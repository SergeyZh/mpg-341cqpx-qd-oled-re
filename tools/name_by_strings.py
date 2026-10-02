#!/usr/bin/env python3
"""Derive function names from the debug strings a SPARC firmware references.

The firmware ships with tracing enabled, so most driver functions build a
pointer to their own name and pass it to the debug printf. Decoding the
`sethi %hi(X)` / `or %r, %lo(X), %r` pairs recovers X; when X is the start of a
string that looks like a C identifier, the enclosing function is almost
certainly that function.

Emits CSV `address,name` for tools/ghidra_scripts/ApplyNames.java.

    tools/name_by_strings.py FW.bin --start 0x50000 --end 0xa5600 \
        --base 0xA0060000 -o out/names_leon2sub.csv
"""
import argparse
import collections
import re


def func_starts(d, R, E):
    """Function entry offsets: `save %sp,-N,%sp` prologues plus call targets."""
    s = set()
    for i in range(R, E - 3, 4):
        v = int.from_bytes(d[i : i + 4], "big")
        if ((v >> 30) == 2 and ((v >> 19) & 0x3F) == 0x3C and (v & 0x2000)
                and ((v >> 25) & 0x1F) == 14 and ((v >> 14) & 0x1F) == 14):
            s.add(i)
        elif (v >> 30) == 1:
            disp = v & 0x3FFFFFFF
            if disp & 0x20000000:
                disp -= 0x40000000
            t = i + 4 * disp
            if R <= t < E:
                s.add(t)
    return sorted(s)


def sethi_refs(d, R, E):
    """(instruction offset, absolute address) for each sethi/or constant."""
    out = []
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
            if (w >> 30) != 2 or not (w & 0x2000) or ((w >> 14) & 0x1F) != rd:
                continue
            if ((w >> 19) & 0x3F) == 0x02:  # or -> building a constant
                lo = w & 0x1FFF
                if lo & 0x1000:
                    lo -= 0x2000
                out.append((i, hi + lo))
            break
    return out


# Many trace strings are decorated: an ANSI colour prefix, then the function
# name, then a short suffix such as " %d", "()" or ": ". Strip the decoration
# and keep the identifier, but only when the identifier is what the string is
# essentially about -- otherwise a format string would masquerade as a name.
ANSI = re.compile(rb"^(?:\x1b?\[[0-9;]*m)+")
IDENT = re.compile(rb"[A-Za-z_][A-Za-z0-9_]{5,63}")


def name_at(d, off):
    """Return the function name a NUL-terminated string here denotes, if any."""
    raw = d[off : off + 96]
    end = raw.find(b"\x00")
    if end < 0:
        return None
    raw = raw[:end]
    body = ANSI.sub(b"", raw)
    m = IDENT.match(body)
    if not m:
        return None
    s = m.group(0)
    # The identifier must dominate: at most a short decorative tail.
    tail = body[len(s) :].strip()
    if len(tail) > 8:
        return None
    name = s.decode()
    if "_" not in name and not (any(c.islower() for c in name)
                                and any(c.isupper() for c in name)):
        return None
    return name


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--start", type=lambda x: int(x, 0), required=True)
    ap.add_argument("--end", type=lambda x: int(x, 0), required=True)
    ap.add_argument("--base", type=lambda x: int(x, 0), required=True)
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args()

    d = open(args.image, "rb").read()
    R, E, B = args.start, args.end, args.base

    starts = func_starts(d, R, E)
    refs = sethi_refs(d, R, E)
    print(f"function starts: {len(starts)}   sethi/or constants: {len(refs)}")

    import bisect

    # name -> set of enclosing function offsets that reference it
    cand = collections.defaultdict(set)
    for ins_off, addr in refs:
        str_off = addr - B + R
        if not (0 <= str_off < len(d)):
            continue
        nm = name_at(d, str_off)
        if not nm:
            continue
        k = bisect.bisect_right(starts, ins_off) - 1
        if k < 0:
            continue
        cand[nm].add(starts[k])

    rows = []
    ambiguous = 0
    taken = {}
    for nm, fns in sorted(cand.items()):
        if len(fns) != 1:
            ambiguous += 1
            continue
        f = next(iter(fns))
        if f in taken:  # two names for one function -- keep the longer one
            if len(nm) <= len(taken[f]):
                continue
        taken[f] = nm
    for f, nm in taken.items():
        rows.append((B + (f - R), nm))

    rows.sort()
    with open(args.out, "w") as fh:
        fh.write("address,name\n")
        for a, nm in rows:
            fh.write(f"0x{a:08X},{nm}\n")
    print(f"resolved {len(rows)} function names "
          f"({ambiguous} names referenced from several functions, skipped)")
    print(f"wrote {args.out}")
    for a, nm in rows[:15]:
        print(f"   0x{a:08X}  {nm}")


if __name__ == "__main__":
    main()
