#!/usr/bin/env python3
"""Extract the OSD fonts from a Novatek NT68503 image (Leon2 Main).

The OSD controller has no font of its own: its pattern RAM is filled by the
CPU. The glyphs live in the Leon2 Main image and are read with plain
lduh/ldub through fifteen pairs of six-instruction accessor stubs, one pair
per font. A font is selected by a control byte 0xF0..0xFF inside the string
itself; two switch statements map that byte to the stubs.

Per font there are two tables:

    bitmap   u16 per row, index = code * 18 + row, MSB is the leftmost pixel
    widths   u8 per code, the advance in pixels (the font is proportional)

Height is 18 rows for every font. That is verified for the default font
(0xF0) by rendering, and holds for the rest: the blank-row periodogram of
every table peaks at 18, and for 0xF2, 0xF3 and 0xFD the table size is an
exact multiple of 18 * 2 * (number of width entries).

Nothing is hard-coded to one image. The stubs are found by their shape, the
switch tables by the `add %rs,-0xf0,%g1` that precedes them, so the script
works on any image where the same code is present.

Usage:
    tools/font.py FIRMWARE.bin -o out/fonts

Writes per font, named by its control byte:

    fontF0.png       glyph sheet, 16 glyphs per row, index = row*16 + col
    fontF0.bin       raw bitmap table, big-endian u16 per row
    fontF0.widths    raw width table, one byte per glyph
    fonts.csv        index: control byte, addresses, glyph count
"""
import argparse
import os
import struct
import zlib

MAIN = 0x108000        # file offset of Leon2 Main address 0
HEIGHT = 18            # rows per glyph, see module docstring
CELL_W = 16            # bits stored per row; the OSD cell itself is 12 wide
CELL = 12              # OSD cell width in pixels

RETL = 0x81C3E008      # jmpl %o7+8,%g0


def sx13(v):
    return v - 0x2000 if v & 0x1000 else v


def words_of(fw):
    img = memoryview(fw)[MAIN:]
    n = len(img) // 4
    return struct.unpack(">%dI" % n, img[:n * 4])


def find_stubs(words):
    """Locate the accessor stubs.

    Each is `sethi %hi(T),%g1 / ... / or %g1,%lo(T),%g1 / retl / ld[uh|ub]`.
    Returns {stub address: (kind, table)}, kind being 'bitmap' or 'width'.
    """
    out = {}
    for i in range(len(words) - 5):
        w = words[i]
        if (w >> 30) != 0 or (w >> 22) & 7 != 4 or (w >> 25) & 31 != 1:
            continue                                   # sethi ...,%g1
        hi = (w & 0x3FFFFF) << 10
        for j in range(i + 1, i + 4):
            y = words[j]
            if (y >> 30) == 2 and (y >> 19) & 0x3F == 0x02 \
                    and (y >> 13) & 1 and (y >> 25) & 31 == 1 \
                    and (y >> 14) & 31 == 1:           # or %g1,%lo,%g1
                break
        else:
            continue
        if words[j + 1] != RETL:
            continue
        ld = words[j + 2]
        if (ld >> 30) != 3 or (ld >> 13) & 1:
            continue
        op3 = (ld >> 19) & 0x3F
        if op3 not in (0x01, 0x02):                    # ldub / lduh
            continue
        if 1 not in ((ld >> 14) & 31, ld & 31):        # indexed through %g1
            continue
        # the stub itself starts one instruction earlier, at `sll %o0,0x10,%o0`
        out[(i - 1) * 4] = ('width' if op3 == 0x01 else 'bitmap',
                            hi + sx13(y & 0x1FFF))
    return out


def find_switch(words):
    """Locate both `switch (control_byte)` dispatchers.

    Both start with `add %rs,-0xf0,%g1 / cmp %g1,0xf`, then build the jump
    table address and index it. Returns a list of {control byte: stub}.
    """
    tables = []
    for i in range(len(words) - 6):
        w = words[i]
        if (w >> 30) != 2 or (w >> 19) & 0x3F != 0x00 or not (w >> 13) & 1:
            continue
        if (w >> 25) & 31 != 1 or sx13(w & 0x1FFF) != -0xF0:   # add ...,-0xf0,%g1
            continue
        nxt = words[i + 1]
        if (nxt >> 30) != 2 or (nxt >> 19) & 0x3F != 0x14 \
                or not (nxt >> 13) & 1 or (nxt & 0x1FFF) != 0x0F:
            continue                                           # cmp %g1,0xf
        hi = None
        for j in range(i + 2, i + 8):
            y = words[j]
            if (y >> 30) == 0 and (y >> 22) & 7 == 4:
                hi = (y & 0x3FFFFF) << 10
            elif hi is not None and (y >> 30) == 2 \
                    and (y >> 19) & 0x3F == 0x02 and (y >> 13) & 1:
                jt = hi + sx13(y & 0x1FFF)
                break
        else:
            continue
        cases = {}
        for k in range(16):
            case = words[jt // 4 + k]
            for m in range(case // 4, case // 4 + 5):
                if (words[m] >> 30) == 1:              # call, 30-bit signed disp
                    disp = words[m] & 0x3FFFFFFF
                    if disp & 0x20000000:
                        disp -= 0x40000000
                    cases[0xF0 + k] = (m + disp) * 4
                    break
        if len(cases) == 16:
            tables.append(cases)
    return tables


def find_fonts(fw):
    """Return [(control byte, bitmap table, width table, glyph count)]."""
    words = words_of(fw)
    stubs = find_stubs(words)
    switches = find_switch(words)
    if len(switches) != 2:
        raise SystemExit("expected 2 font dispatchers, found %d" % len(switches))

    kinds = {}
    for cases in switches:
        by_kind = {stubs[s][0] for s in cases.values() if s in stubs}
        if len(by_kind) != 1:
            raise SystemExit("dispatcher mixes stub kinds: %s" % by_kind)
        kinds[by_kind.pop()] = {c: stubs[s][1] for c, s in cases.items()}
    if set(kinds) != {'bitmap', 'width'}:
        raise SystemExit("missing a dispatcher: %s" % sorted(kinds))

    bounds = sorted(set(kinds['bitmap'].values()) | set(kinds['width'].values()))
    fonts, seen = [], {}
    for code in sorted(kinds['bitmap']):
        bmp = kinds['bitmap'][code]
        if bmp in seen:                      # 0xF0 and 0xF1 share the default case
            seen[bmp].append(code)
            continue
        after = [a for a in bounds if a > bmp]
        end = after[0] if after else zero_run(fw, bmp)
        count = (end - bmp) // (2 * HEIGHT)
        while count and not any(glyph(fw, bmp, count - 1)):
            count -= 1                       # drop the padding after the last glyph
        seen[bmp] = [code]
        fonts.append([seen[bmp], bmp, kinds['width'][code], count])
    return fonts


def zero_run(fw, start, run=64):
    """End of the last table: the first long run of zero bytes after it."""
    p = MAIN + start
    zeros = 0
    while p < len(fw):
        zeros = zeros + 1 if fw[p] == 0 else 0
        if zeros == run:
            return p - run - MAIN
        p += 1
    return len(fw) - MAIN


def glyph(fw, bmp, code):
    off = MAIN + bmp + code * HEIGHT * 2
    return struct.unpack_from(">%dH" % HEIGHT, fw, off)


PALETTE = {
    'bg':   (0xFF, 0xFF, 0xFF),
    'ink':  (0x11, 0x11, 0x11),
    'over': (0xE8, 0xE8, 0xE8),      # columns past the advance width
    'cell': (0xF6, 0xD9, 0xD9),      # columns past the 12 px OSD cell
    'grid': (0xA0, 0xA0, 0xA0),
}


def sheet(fw, bmp, widths, count, cols=16):
    """Glyph sheet: one pixel per pixel, 1 px grid, advance width shaded."""
    rows = (count + cols - 1) // cols
    w = cols * (CELL_W + 1) + 1
    h = rows * (HEIGHT + 1) + 1
    img = [[PALETTE['bg']] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            if y % (HEIGHT + 1) == 0 or x % (CELL_W + 1) == 0:
                img[y][x] = PALETTE['grid']
    for c in range(count):
        gx = (c % cols) * (CELL_W + 1) + 1
        gy = (c // cols) * (HEIGHT + 1) + 1
        adv = widths[c] if c < len(widths) else CELL_W
        bits = glyph(fw, bmp, c)
        for r in range(HEIGHT):
            for b in range(CELL_W):
                if bits[r] & (0x8000 >> b):
                    px = PALETTE['ink']
                elif b >= adv:
                    px = PALETTE['over']
                elif b >= CELL:
                    px = PALETTE['cell']
                else:
                    continue
                img[gy + r][gx + b] = px
    return img


def write_png(path, img):
    h, w = len(img), len(img[0])
    raw = bytearray()
    for row in img:
        raw.append(0)
        for px in row:
            raw += bytes(px)

    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c))

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)))
        f.write(chunk(b"IDAT", zlib.compress(bytes(raw), 9)))
        f.write(chunk(b"IEND", b""))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("firmware")
    ap.add_argument("-o", "--out", default="out/fonts")
    args = ap.parse_args()

    fw = open(args.firmware, "rb").read()
    fonts = find_fonts(fw)
    os.makedirs(args.out, exist_ok=True)

    index = ["codes,bitmap,widths,glyphs,height,bitmap_file_off,widths_file_off"]
    for codes, bmp, wid, count in fonts:
        widths = fw[MAIN + wid:MAIN + wid + count]
        name = os.path.join(args.out, "font%02X" % codes[0])
        with open(name + ".bin", "wb") as f:
            f.write(fw[MAIN + bmp:MAIN + bmp + count * HEIGHT * 2])
        with open(name + ".widths", "wb") as f:
            f.write(widths)
        write_png(name + ".png", sheet(fw, bmp, widths, count))
        tag = " ".join("0x%02X" % c for c in codes)
        index.append("%s,0x%06X,0x%06X,%d,%d,0x%06X,0x%06X"
                     % (tag, bmp, wid, count, HEIGHT, MAIN + bmp, MAIN + wid))
        print("%-9s растр 0x%06X  ширины 0x%06X  %3d глифов  -> %s.png"
              % (tag, bmp, wid, count, os.path.basename(name)))

    with open(os.path.join(args.out, "fonts.csv"), "w") as f:
        f.write("\n".join(index) + "\n")
    print("%d шрифтов -> %s" % (len(fonts), args.out))


if __name__ == "__main__":
    main()
