#!/usr/bin/env python3
"""Map and unpack a Novatek NT68503 scaler firmware image.

Usage:
    tools/fwmap.py FIRMWARE.bin [-o out/]

Prints the image layout (data/erased regions, partition table, config blocks,
per-region CPU guess) and, with -o, writes each region to a file.
"""
import argparse
import collections
import math
import os
import struct

MAGIC = b"\x55\xaa\x66\x99"

# Partition ids seen in this image. Names are provisional: the loader's own
# table is not self-describing, so these come from matching sizes against the
# regions and from strings found inside each one.
PART_NAMES = {
    0x01: "stbc-main (8051)",
    0x02: "stbc-aux (8051)",
    0x03: "tensilica (Xtensa LE)",
    0x05: "leon2-sub (SPARC BE)",
    0x0A: "config/misc",
    0x0B: "HDR runtime (SPARC BE @0x9F1B0000)",
    0x0D: "Leon2 Main service runtime (SPARC BE @0xA0028000)",
    0x0E: "VERSION/config",
    0x10: "leon2-main (SPARC BE)",
}


def entropy(b):
    if not b:
        return 0.0
    c = collections.Counter(b)
    n = len(b)
    return -sum((v / n) * math.log2(v / n) for v in c.values())


def regions(d, gran=256):
    """Split the image into runs of erased (0xFF) and non-erased bytes."""
    out = []
    cur = None
    start = 0
    for i in range(0, len(d), gran):
        blk = d[i : i + gran]
        erased = blk.count(0xFF) == len(blk)
        if erased != cur:
            if cur is not None:
                out.append((start, i, cur))
            cur, start = erased, i
    out.append((start, len(d), cur))
    return out


def sparc_ratio(d, a, b):
    """Fraction of aligned words that decode as plausible SPARC v8 opcodes."""
    good = total = 0
    alu = {0x00, 0x02, 0x04, 0x05, 0x07, 0x0E, 0x10, 0x12, 0x14, 0x16, 0x17,
           0x1A, 0x1E, 0x25, 0x26, 0x27, 0x38, 0x3C, 0x3D}
    ldst = {0, 1, 2, 3, 4, 5, 6, 7, 0x0D, 0x0F}
    for i in range(a, min(b, len(d)) - 3, 4):
        v = int.from_bytes(d[i : i + 4], "big")
        total += 1
        op = v >> 30
        op3 = (v >> 19) & 0x3F
        if op == 1:
            good += 1
        elif op == 0 and ((v >> 22) & 7) in (2, 4):
            good += 1
        elif op == 2 and op3 in alu:
            good += 1
        elif op == 3 and op3 in ldst:
            good += 1
    return good / total if total else 0.0


def guess_cpu(d, a, b):
    if b - a < 1024:
        return "data"
    r = sparc_ratio(d, a, b)
    if r > 0.70:
        return f"SPARC BE ({r:.0%})"
    s = d[a:b]
    # 8051: MOV DPTR (0x90) and LCALL (0x12) are unusually dense in Keil output.
    dens = (s.count(b"\x90") + s.count(b"\x12")) * 10000 // len(s)
    if dens > 150:
        return f"8051 (density {dens}/10k)"
    return f"data/mixed (sparc {r:.0%})"


def parse_partitions(d, off=0x6000, limit=0x400):
    """Loader partition table: u16 id, u16 flags, u32 size, terminated by 0."""
    parts = []
    for i in range(off, off + limit, 8):
        pid, flags, size = struct.unpack_from(">HHI", d, i)
        if pid == 0 and size == 0:
            break
        if pid == 0xFFFF:
            break
        parts.append((i, pid, flags, size))
    return parts


def parse_config(d):
    """Novatek 55AA6699 config blocks: magic, ASCII tag, len, payload."""
    out = []
    pos = 0
    while True:
        pos = d.find(MAGIC, pos)
        if pos < 0:
            break
        tag = bytearray()
        i = pos + 4
        while i < len(d) and 32 <= d[i] < 127 and len(tag) < 16:
            tag.append(d[i])
            i += 1
        payload = d[i : i + 24]
        out.append((pos, tag.decode("ascii", "replace"), payload))
        pos += 4
    return out


def parse_jedec(d, off=0x4000, limit=0x200):
    """SPI flash ID table: idx, manufacturer, dev hi, dev lo, size code, flags."""
    out = []
    for i in range(off, off + limit, 6):
        r = d[i : i + 6]
        if len(r) < 6 or r == b"\xff" * 6:
            break
        out.append((i, r[0], r[1], r[2], r[3], r[4], r[5]))
    return out


MFG = {0xBF: "SST", 0xC2: "Macronix", 0xEF: "Winbond", 0x1C: "EON",
       0x37: "AMIC", 0x8C: "ESMT", 0xC8: "GigaDevice", 0xD5: "ISSI",
       0xA1: "Fudan", 0x20: "Micron", 0x01: "Spansion"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("-o", "--outdir", help="write regions here")
    args = ap.parse_args()

    d = open(args.image, "rb").read()
    print(f"image: {args.image}  size {len(d)} (0x{len(d):x})\n")

    print("== partition table @0x6000 ==")
    parts = parse_partitions(d)
    total = 0
    for off, pid, flags, size in parts:
        total += size
        name = PART_NAMES.get(pid, "?")
        print(f"  @0x{off:06x}  id=0x{pid:02x}  flags=0x{flags:04x}  "
              f"size={size:>9} (0x{size:06x})  {name}")
    print(f"  {len(parts)} partitions, total {total} bytes "
          f"({total * 100 // len(d)}% of image)\n")

    print("== SPI flash JEDEC id table @0x4000 ==")
    jed = parse_jedec(d)
    print(f"  {len(jed)} entries, manufacturers: "
          + ", ".join(sorted({MFG.get(e[2], f"0x{e[2]:02x}") for e in jed})))
    print()

    print("== config blocks (55 AA 66 99) ==")
    for off, tag, payload in parse_config(d):
        txt = "".join(chr(c) if 32 <= c < 127 else "." for c in payload)
        print(f"  @0x{off:06x}  {tag:<10} {payload[:16].hex(' ')}  |{txt}|")
    print()

    print("== image layout ==")
    data_total = 0
    rows = []
    for a, b, erased in regions(d):
        if b - a < 256:
            continue
        if erased:
            rows.append((a, b, "ERASED", "", ""))
        else:
            data_total += b - a
            rows.append((a, b, "DATA", f"{entropy(d[a:b]):.2f}", guess_cpu(d, a, b)))
    for a, b, kind, ent, cpu in rows:
        if kind == "ERASED":
            print(f"  0x{a:06x}-0x{b:06x}  {b - a:>9}  ERASED")
        else:
            print(f"  0x{a:06x}-0x{b:06x}  {b - a:>9}  DATA  H={ent}  {cpu}")
    print(f"\n  data {data_total} bytes, erased {len(d) - data_total} bytes")
    print(f"  partition table accounts for {total} of {data_total} data bytes "
          f"({total * 100 // data_total}%)")

    if args.outdir:
        os.makedirs(args.outdir, exist_ok=True)
        n = 0
        for a, b, erased in regions(d):
            if erased or b - a < 1024:
                continue
            path = os.path.join(args.outdir, f"region_{a:06x}_{b:06x}.bin")
            open(path, "wb").write(d[a:b])
            n += 1
        print(f"\nwrote {n} regions to {args.outdir}/")

        # Two images do not coincide with a region: an erased gap splits the
        # STBC AUX partition in two, and Leon2 Main is the whole flash tail.
        # Both are cut by partition instead, and ghidra_import.sh expects them.
        for name, a, b in (("stbc_aux_020000", 0x020000, 0x02E552),
                           ("leon2main_108000", 0x108000, len(d))):
            open(os.path.join(args.outdir, name + ".bin"), "wb").write(d[a:b])
        print("wrote stbc_aux_020000.bin, leon2main_108000.bin")


if __name__ == "__main__":
    main()
