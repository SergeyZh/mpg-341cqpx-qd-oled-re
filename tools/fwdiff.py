#!/usr/bin/env python3
"""Compare two firmware images and report what changed, by region.

Two modes, because they answer different questions:

--bytes    Changed byte runs grouped by the regions in docs/firmware-map.md.
           Only meaningful when the builds are the same length. A rebuild
           almost always shifts code, and then everything after the first
           insertion reads as "changed" and the output is worthless.

--strings  Set difference over printable strings. Immune to shifting, so this
           is the mode that actually says what changed functionally. Much of
           the delta is binary noise that happens to be printable -- look for
           identifiers and messages.

Default is both.

    tools/fwdiff.py OLD.bin NEW.bin [--bytes] [--strings] [--min-run 16]
"""
import argparse
import re

# (start, end, name) in the FW.037 layout. Ends are exclusive.
REGIONS = [
    (0x000000, 0x001900, "8051 STBC bootloader"),
    (0x004000, 0x004200, "SPI flash JEDEC id table"),
    (0x006000, 0x008000, "partition table"),
    (0x010000, 0x01F100, "8051 partition id=0x01"),
    (0x020000, 0x02E600, "8051 partition id=0x02"),
    (0x030000, 0x03D900, "Tensilica Xtensa LE (LDC/ABL)"),
    (0x050000, 0x0A5600, "Leon2 Sub code (base 0xA0060000)"),
    (0x0A6000, 0x0A8800, "Leon2 Sub pointer table"),
    (0x0B0000, 0x0CF500, "partition id=0x0B"),
    (0x0D0000, 0x0D8100, "second trap table region"),
    (0x0EC000, 0x0F1B00, "VERSION config block"),
    (0x118000, 0x11F800, "EDID tables (Main addr 0x010000)"),
    (0x11A000, 0x128000, "data"),
    (0x1281C0, 0x200000, "Leon2 Main code (base 0)"),
    (0x200000, 0x26A200, "Leon2 Main resources / OSD / config"),
]


def region_of(off):
    for a, b, name in REGIONS:
        if a <= off < b:
            return name
    return "unmapped"


def build_stamp(d):
    m = re.search(rb"[A-Z][a-z]{2} [0-9 ][0-9] 20[0-9]{2}\x00", d)
    t = re.search(rb"[01][0-9]:[0-5][0-9]:[0-5][0-9]\x00", d)
    return ((m.group(0)[:-1].decode() if m else "?")
            + " " + (t.group(0)[:-1].decode() if t else ""))


def cfg(d, tag):
    k = d.find(b"\x55\xaa\x66\x99" + tag)
    if k < 0:
        return None
    payload = d[k + 4 + len(tag) + 1 : k + 4 + len(tag) + 32]
    return payload.split(b"\x00")[0].decode("ascii", "replace")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("old")
    ap.add_argument("new")
    ap.add_argument("--min-run", type=int, default=16,
                    help="merge changed bytes closer together than this")
    ap.add_argument("--bytes", action="store_true", help="byte-run diff")
    ap.add_argument("--strings", action="store_true", help="string set diff")
    args = ap.parse_args()
    if not args.bytes and not args.strings:
        args.bytes = args.strings = True

    a = open(args.old, "rb").read()
    b = open(args.new, "rb").read()
    print(f"old {args.old}: {len(a)} bytes (0x{len(a):x})")
    print(f"new {args.new}: {len(b)} bytes (0x{len(b):x})")
    print(f"  build stamp: {build_stamp(a)}   ->   {build_stamp(b)}")
    for tag in (b"SCALER", b"PANEL", b"UART"):
        print(f"  {tag.decode():<7}: {cfg(a, tag)!r}  ->  {cfg(b, tag)!r}")
    if a == b:
        print("\nimages are identical")
        return

    if args.strings:
        pat = re.compile(rb"[ -~]{6,}")
        sa = {m.group(0).decode() for m in pat.finditer(a)}
        sb = {m.group(0).decode() for m in pat.finditer(b)}
        # Noise strings are short and lack the shape of a message: require a
        # space or an underscore and mostly-letters to be worth printing.
        def meaningful(s):
            letters = sum(c.isalpha() or c.isspace() for c in s)
            return len(s) >= 8 and letters * 100 // len(s) >= 70 \
                   and (" " in s or "_" in s or s.isalnum())
        print(f"\n== strings: old {len(sa)}, new {len(sb)}, common {len(sa & sb)} ==")
        for label, delta in (("only in NEW", sb - sa), ("only in OLD", sa - sb)):
            keep = sorted(s for s in delta if meaningful(s))
            print(f"\n  {label}: {len(delta)} total, {len(keep)} look meaningful")
            for s in keep:
                print(f"    {s[:110]}")

    if not args.bytes:
        return

    n = min(len(a), len(b))
    if len(a) != len(b):
        print(f"\n!! images differ in length by {abs(len(a) - len(b))} bytes -- "
              f"code is shifted, so the byte diff below is dominated by "
              f"misalignment and should not be read as real change")
    # Collect changed byte runs, merging ones separated by a short gap.
    runs = []
    i = 0
    while i < n:
        if a[i] != b[i]:
            j = i
            gap = 0
            k = i
            while k < n and gap <= args.min_run:
                if a[k] != b[k]:
                    j = k
                    gap = 0
                else:
                    gap += 1
                k += 1
            runs.append((i, j + 1))
            i = j + 1
        else:
            i += 1
    if len(b) != len(a):
        runs.append((n, max(len(a), len(b))))

    changed = sum(e - s for s, e in runs)
    print(f"\n{len(runs)} changed runs, {changed} bytes differ "
          f"({changed * 100 // n}% of the overlap)\n")

    by_region = {}
    for s, e in runs:
        by_region.setdefault(region_of(s), [0, 0])
        by_region[region_of(s)][0] += 1
        by_region[region_of(s)][1] += e - s
    print("== changes by region ==")
    for name in [r[2] for r in REGIONS] + ["unmapped"]:
        if name in by_region:
            cnt, size = by_region[name]
            print(f"  {name:<42} {cnt:5d} runs  {size:8d} bytes")

    print("\n== largest individual runs ==")
    for s, e in sorted(runs, key=lambda r: r[1] - r[0], reverse=True)[:20]:
        print(f"  0x{s:06x}-0x{e:06x}  {e - s:7d} bytes  {region_of(s)}")


if __name__ == "__main__":
    main()
