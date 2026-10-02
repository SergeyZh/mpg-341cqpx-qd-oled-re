#!/usr/bin/env python3
"""Extract and decode every EDID in a Novatek scaler firmware image.

Handles base EDID 1.x blocks, CTA-861 extensions (incl. VIC lists and the
HDMI 2.1 / VRR vendor blocks) and DisplayID 2.0 extensions, then reports the
highest refresh rate the firmware actually advertises.

Usage:
    tools/edid.py FIRMWARE.bin [--dump out/edid]
"""
import argparse
import collections
import os

HDR = b"\x00\xff\xff\xff\xff\xff\xff\x00"

# CTA-861 VIC -> (h, v, refresh). Only the entries that show up on a 21:9
# 240 Hz panel plus the common ones; unknown VICs are reported as raw numbers.
VIC = {
    1: (640, 480, 60), 4: (1280, 720, 60), 16: (1920, 1080, 60),
    31: (1920, 1080, 50), 34: (1920, 1080, 30), 63: (1920, 1080, 120),
    64: (1920, 1080, 100), 97: (3840, 2160, 60), 95: (3840, 2160, 30),
    94: (3840, 2160, 25), 93: (3840, 2160, 24), 96: (3840, 2160, 50),
    117: (3840, 2160, 120), 118: (3840, 2160, 100),
}


def mfg_id(b):
    v = int.from_bytes(b[8:10], "big")
    return "".join(chr(((v >> s) & 31) + 64) for s in (10, 5, 0))


def dtd(t):
    """Decode an 18-byte EDID detailed timing descriptor."""
    pc = (t[1] << 8 | t[0]) * 10  # kHz
    if pc == 0:
        return None
    ha = t[2] | ((t[4] >> 4) << 8)
    hb = t[3] | ((t[4] & 15) << 8)
    va = t[5] | ((t[7] >> 4) << 8)
    vb = t[6] | ((t[7] & 15) << 8)
    ht, vt = ha + hb, va + vb
    if ht < 100 or vt < 100:
        return None
    return dict(h=ha, v=va, htotal=ht, vtotal=vt, pclk=pc,
                hz=pc * 1000.0 / (ht * vt))


def parse_base(b):
    """Base EDID block: name, serial, range limits, detailed timings."""
    info = dict(mfg=mfg_id(b), product=int.from_bytes(b[10:12], "little"),
                version=f"{b[18]}.{b[19]}", name=None, limits=None, dtds=[],
                extensions=b[126])
    for k in range(54, 126, 18):
        t = b[k : k + 18]
        if t[0:2] != b"\x00\x00":
            d = dtd(t)
            if d:
                info["dtds"].append(d)
            continue
        tag = t[3]
        if tag == 0xFC:  # display name
            info["name"] = t[5:18].split(b"\n")[0].decode("ascii", "replace").strip()
        elif tag == 0xFD:  # range limits
            voff = t[4] & 3
            hoff = (t[4] >> 2) & 3
            info["limits"] = dict(
                vmin=t[5] + (255 if voff in (1, 3) else 0),
                vmax=t[6] + (255 if voff == 3 else 0),
                hmin=t[7] + (255 if hoff in (1, 3) else 0),
                hmax=t[8] + (255 if hoff == 3 else 0),
                pclk_max=t[9] * 10,
            )
    return info


def parse_cta(b):
    """CTA-861 extension: VIC short descriptors, vendor blocks, DTDs."""
    out = dict(vics=[], dtds=[], vendor=[], vrr=None)
    dtd_off = b[2]
    i = 4
    end = dtd_off if 4 < dtd_off <= 127 else 4
    while i < end:
        tag = b[i] >> 5
        ln = b[i] & 31
        payload = b[i + 1 : i + 1 + ln]
        if tag == 2:  # video data block
            out["vics"] += [v & 0x7F for v in payload]
        elif tag == 3 and len(payload) >= 3:  # vendor specific
            oui = payload[:3][::-1].hex()
            out["vendor"].append(oui)
            # HDMI Forum VSDB (OUI C4-5D-D8) carries the VRR min/max fields.
            if oui == "c45dd8" and len(payload) >= 11:
                vmin = payload[9] & 0x3F
                vmax = payload[10] | ((payload[9] & 0xC0) << 2)
                out["vrr"] = (vmin, vmax)
        elif tag == 7 and ln >= 1 and payload[0] == 0:  # extended: video cap
            pass
        i += 1 + ln
    if dtd_off >= 4:
        k = dtd_off
        while k + 18 <= 127:
            t = b[k : k + 18]
            if t[0:2] == b"\x00\x00":
                break
            d = dtd(t)
            if d:
                out["dtds"].append(d)
            k += 18
    return out


def did_type1(t):
    """DisplayID Type I detailed timing, 20 bytes. All counts are stored -1."""
    pc = (int.from_bytes(t[0:3], "little") + 1) * 10  # kHz
    ha = int.from_bytes(t[4:6], "little") + 1
    hb = int.from_bytes(t[6:8], "little") + 1
    va = int.from_bytes(t[12:14], "little") + 1
    vb = int.from_bytes(t[14:16], "little") + 1
    ht, vt = ha + hb, va + vb
    if ht < 100 or vt < 100 or pc < 1000:
        return None
    return dict(h=ha, v=va, htotal=ht, vtotal=vt, pclk=pc,
                hz=pc * 1000.0 / (ht * vt), preferred=bool(t[3] & 0x80))


def parse_displayid(b):
    """DisplayID extension block carried inside an EDID extension.

    This firmware uses DisplayID 1.2 (b[1] == 0x12) with Type I Detailed
    Timing blocks (tag 0x03); DisplayID 2.0 renumbered the same payload to
    tag 0x20, so both are accepted.
    """
    out = dict(version=b[1], timings=[])
    n = b[2]
    i = 5
    end = min(5 + n, 126)
    while i + 3 <= end:
        tag, _rev, ln = b[i], b[i + 1], b[i + 2]
        if ln == 0 or i + 3 + ln > end:
            break
        blk = b[i + 3 : i + 3 + ln]
        if tag in (0x03, 0x20):
            for k in range(0, len(blk) - 19, 20):
                t = did_type1(blk[k : k + 20])
                if t:
                    out["timings"].append(t)
        i += 3 + ln
    return out


def checksum_ok(b):
    return sum(b) & 0xFF == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--dump", help="write each full EDID here")
    args = ap.parse_args()
    d = open(args.image, "rb").read()

    bases = [o for o in range(0, len(d) - 128, 128) if d[o : o + 8] == HDR]
    print(f"found {len(bases)} base EDID blocks\n")

    all_dtd = collections.Counter()
    limits = collections.Counter()
    vic_seen = collections.Counter()
    vrr_seen = collections.Counter()
    did_timings = collections.Counter()
    names = collections.Counter()
    groups = collections.Counter()

    for o in bases:
        b = d[o : o + 128]
        info = parse_base(b)
        names[(info["mfg"], f"0x{info['product']:04x}", info["name"])] += 1
        groups[info["mfg"]] += 1
        for t in info["dtds"]:
            all_dtd[(t["h"], t["v"], round(t["hz"], 2), t["pclk"])] += 1
        if info["limits"]:
            L = info["limits"]
            limits[(L["vmin"], L["vmax"], L["hmin"], L["hmax"], L["pclk_max"])] += 1
        # Walk the declared extension blocks that follow.
        for e in range(1, info["extensions"] + 1):
            eo = o + 128 * e
            if eo + 128 > len(d):
                break
            eb = d[eo : eo + 128]
            if eb[0] == 0x02:
                c = parse_cta(eb)
                for v in c["vics"]:
                    vic_seen[v] += 1
                for t in c["dtds"]:
                    all_dtd[(t["h"], t["v"], round(t["hz"], 2), t["pclk"])] += 1
                if c["vrr"]:
                    vrr_seen[c["vrr"]] += 1
            elif eb[0] == 0x70:
                for t in parse_displayid(eb)["timings"]:
                    did_timings[(t["h"], t["v"], round(t["hz"], 2), t["pclk"])] += 1

        if args.dump:
            os.makedirs(args.dump, exist_ok=True)
            total = 128 * (1 + info["extensions"])
            open(os.path.join(args.dump, f"edid_{o:06x}.bin"), "wb").write(
                d[o : o + total])

    print("== manufacturers / product / name ==")
    for (m, p, n), c in names.most_common():
        print(f"  {m} {p}  {n!r:<20} x{c}")

    print("\n== detailed timings (base EDID + CTA DTDs) ==")
    for (h, v, hz, pc), c in sorted(all_dtd.items(), key=lambda r: -r[0][2]):
        print(f"  {h:>5}x{v:<5} {hz:>7.2f} Hz  pclk {pc/1000:>8.3f} MHz  x{c}")

    if did_timings:
        print("\n== DisplayID detailed timings ==")
        for (h, v, hz, pc), c in sorted(did_timings.items(), key=lambda r: -r[0][2]):
            print(f"  {h:>5}x{v:<5} {hz:>7.2f} Hz  pclk {pc/1000:>8.3f} MHz  x{c}")

    print("\n== range limit descriptors ==")
    for (vmin, vmax, hmin, hmax, pmax), c in sorted(limits.items()):
        print(f"  V {vmin:>3}-{vmax:<3} Hz   H {hmin:>3}-{hmax:<3} kHz   "
              f"max pclk {pmax:>5} MHz   x{c}")

    if vrr_seen:
        print("\n== HDMI Forum VRR range ==")
        for (vmin, vmax), c in sorted(vrr_seen.items()):
            print(f"  VRR {vmin}-{vmax} Hz   x{c}")

    if vic_seen:
        print("\n== CTA VICs ==")
        for v, c in sorted(vic_seen.items()):
            desc = VIC.get(v)
            s = f"{desc[0]}x{desc[1]}@{desc[2]}" if desc else "?"
            print(f"  VIC {v:>3}  {s:<18} x{c}")

    peak_dtd = max((k[2] for k in all_dtd), default=0)
    peak_did = max((k[2] for k in did_timings), default=0)
    peak_lim = max((k[1] for k in limits), default=0)
    print("\n== verdict ==")
    print(f"  highest refresh in any detailed timing : {max(peak_dtd, peak_did):.2f} Hz")
    print(f"  highest refresh in any range limit     : {peak_lim} Hz")
    print(f"  highest max pixel clock declared       : "
          f"{max((k[4] for k in limits), default=0)} MHz")


if __name__ == "__main__":
    main()
