#!/usr/bin/env python3
"""Recover the link base address of a SPARC v8 big-endian firmware region.

Method: a SPARC `call` is PC-relative, so its target's *file offset* is
independent of the load base -- that gives a reliable set of function starts.
Absolute function pointers stored in the image are base-relative. The correct
base is the one that maps the most stored pointers onto known function starts.

    tools/findbase.py FIRMWARE.bin --start 0x50000 --end 0xa5600
"""
import argparse
import collections


def call_targets(d, start, end):
    """File offsets targeted by SPARC call instructions within [start, end)."""
    t = set()
    for i in range(start, end - 3, 4):
        v = int.from_bytes(d[i : i + 4], "big")
        if v >> 30 != 1:
            continue
        disp = v & 0x3FFFFFFF
        if disp & 0x20000000:  # sign-extend disp30
            disp -= 0x40000000
        tgt = i + 4 * disp
        if start <= tgt < end:
            t.add(tgt)
    return t


def save_prologues(d, start, end):
    """Offsets of `save %sp, -N, %sp` -- the classic non-flat function entry."""
    s = set()
    for i in range(start, end - 3, 4):
        v = int.from_bytes(d[i : i + 4], "big")
        # op=10, op3=111100 (save), rd=%sp(14), rs1=%sp(14), i=1
        if (v >> 30) == 2 and ((v >> 19) & 0x3F) == 0x3C and (v & 0x2000):
            if ((v >> 25) & 0x1F) == 14 and ((v >> 14) & 0x1F) == 14:
                s.add(i)
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--start", type=lambda x: int(x, 0), required=True)
    ap.add_argument("--end", type=lambda x: int(x, 0), required=True)
    ap.add_argument("--align", type=lambda x: int(x, 0), default=0x100,
                    help="candidate base alignment (default 0x100)")
    args = ap.parse_args()

    d = open(args.image, "rb").read()
    R, E = args.start, args.end
    size = E - R

    tgts = call_targets(d, R, E)
    saves = save_prologues(d, R, E)
    starts = tgts | saves
    print(f"region 0x{R:x}-0x{E:x} ({size} bytes)")
    print(f"  call targets: {len(tgts)}   save-prologues: {len(saves)}   "
          f"union: {len(starts)}")
    if not starts:
        print("  no function starts found -- region is probably not SPARC code")
        return

    # Absolute addresses the code itself materialises. GCC on SPARC builds a
    # 32-bit constant as `sethi %hi(X), %r` followed (not necessarily
    # immediately) by an `or %r, %lo(X), %r` or a `jmp %r + %lo(X)`. Pairing
    # each sethi with the next instruction that reuses the same register
    # recovers X. These are real references, unlike raw words in the image
    # which are mostly instruction encodings that merely look like pointers.
    addrs = collections.Counter()
    for i in range(R, E - 7, 4):
        v = int.from_bytes(d[i : i + 4], "big")
        if (v >> 30) != 0 or ((v >> 22) & 7) != 4:
            continue
        rd = (v >> 25) & 0x1F
        hi = (v & 0x3FFFFF) << 10
        if hi == 0:
            continue
        for k in range(i + 4, min(i + 24, E - 3), 4):
            w = int.from_bytes(d[k : k + 4], "big")
            if (w >> 30) != 2 or not (w & 0x2000):
                continue
            if ((w >> 14) & 0x1F) != rd:
                continue
            op3 = (w >> 19) & 0x3F
            if op3 in (0x02, 0x38):  # or (build constant) / jmpl (tail call)
                lo = w & 0x1FFF
                if lo & 0x1000:
                    lo -= 0x2000
                addrs[hi + lo] += 1
            break
    print(f"  sethi-derived absolute addresses: {len(addrs)} distinct, "
          f"{sum(addrs.values())} refs")
    words = addrs

    # A base is B = p - (f - R). Assuming the link base is `align`-aligned,
    # only offsets congruent to p modulo `align` can contribute, so bucket the
    # offsets by that residue instead of trying every (pointer, offset) pair.
    A = args.align
    by_res = collections.defaultdict(list)
    for f in starts:
        by_res[(f - R) % A].append(f - R)

    score = collections.Counter()
    for p, n in words.items():
        for off in by_res.get(p % A, ()):
            B = p - off
            if B > 0:
                score[B] += n
    best = sorted(((n, B) for B, n in score.items()), reverse=True)
    print("\n  top base candidates (hits = stored pointers landing on a "
          "function start):")
    for hits, B in best[:8]:
        print(f"    0x{B:08X}   {hits:6d} hits")
    if best:
        hits, B = best[0]
        second = best[1][0] if len(best) > 1 else 0
        print(f"\n  best: 0x{B:08X} with {hits} hits "
              f"({hits / max(second, 1):.1f}x the runner-up)")


if __name__ == "__main__":
    main()
