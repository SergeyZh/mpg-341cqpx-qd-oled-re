#!/usr/bin/env python3
"""Extract the boot logo that ShowLogo() paints, from a Novatek NT68503 image.

The logo is not a bitmap in flash. It is an OSD screen: ShowLogo (Leon2 Main,
0x0002E028 in FW.037) opens two OSD windows, uploads a private tile set into
OSD RAM, and then fills the windows with tile numbers.

    window 0   93 x 18 tiles   "msi" + "MPG" + "MSI PERFORMANCE GAMING"
    window 1   42 x  7 tiles   AMD FreeSync Premium Pro + HDMI badges

Tiles are 12 x 18 pixels. Two banks exist: a 1 bpp bank (27 B/tile) and a
2 bpp bank (54 B/tile, two 27-byte planes). Both are stored RLE-compressed;
only runs of 0x00 and 0xFF are encoded.

No pixel of the 2 bpp bank ever has both planes set, so it is really two
independent one-bit layers sharing a tile set: one carries "msi", the other
"MPG". They exist to be coloured differently.

Everything the script needs is located in the image itself:

  * the descriptor block that Leon2 Main copies to RAM at 0xA8024000 is found
    by its layout (two 12-byte upload descriptors at +0xC0/+0xCC, and so on);
  * the tile maps and the attribute array are read out of ShowLogo's own code,
    which is located through its reference to that block.

Usage:
    tools/logo.py FIRMWARE.bin -o out/logo
"""
import argparse
import os
import struct
import zlib

MAIN = 0x108000        # file offset of Leon2 Main address 0
RAM = (0xA8000000, 0xA8100000)     # Leon2 Main data RAM

TILE_W, TILE_H = 12, 18
BYTES_1BPP = TILE_W * TILE_H // 8          # 27
BYTES_2BPP = TILE_W * TILE_H * 2 // 8      # 54

# Window geometry, taken from the immediates ShowLogo passes to the OSD layer
# (FW.037: 0x0002E0A8 "mov 0x5d" / 0x0002E0B0 "mov 0x12" for window 0,
#  0x0002E238 "mov 0x2a" / 0x0002E240 "mov 7" for window 1).
COLS0, ROWS0 = 0x5D, 0x12
COLS1, ROWS1 = 0x2A, 0x07

# After filling window 1, ShowLogo overwrites columns 0..0x10 of every row with
# tile 0 (0x0002E378 passes a constant 0), which blanks the AMD FreeSync badge
# and leaves only HDMI on screen.  The badge stays in the tile data.
BLANK1 = 0x10

# Descriptor offsets inside the block, in the order ShowLogo uses them.
D_PAL1, D_FONT1 = 0x44, 0x64      # window 1: palette (raw), 1 bpp tiles (RLE)
D_PAL0 = 0x70                     # window 0: palette (raw)
D_FONT0_2BPP, D_FONT0_1BPP = 0xC0, 0xCC


def sx13(v):
    return v - 0x2000 if v & 0x1000 else v


def desc8(fw, off):
    """Plain upload descriptor: {u16 len; u16 osd_addr; u32 src}."""
    n, addr, src = struct.unpack_from(">HHI", fw, off)
    return n, addr, src


def desc12(fw, off):
    """RLE upload descriptor: {u16 len; u8 bank; u8 pad; u32 osd_addr; u32 src}."""
    n, bank, _, addr, src = struct.unpack_from(">HBBII", fw, off)
    return n, bank, addr, src


def find_descriptor_block(fw):
    """Locate the .data image whose runtime address is 0xA8024000."""

    def ok12(o):
        if o + 12 > len(fw):
            return False
        n, bank, addr, src = desc12(fw, o)
        return 0 < n and bank < 4 and fw[o + 3] == 0 and addr < 0x40000 \
            and 0x1000 < src < 0x180000

    def ok8(o):
        if o + 8 > len(fw):
            return False
        n, addr, src = desc8(fw, o)
        return 0 < n and addr < 0x40000 and 0x1000 < src < 0x180000

    hits = [b for b in range(0, len(fw) - 0x100, 4)
            if ok12(b + D_FONT0_2BPP) and ok12(b + D_FONT0_1BPP)
            and ok12(b + D_FONT1) and ok8(b + D_PAL0) and ok8(b + D_PAL1)]
    if len(hits) != 1:
        raise SystemExit("descriptor block: expected 1 candidate, got %d" % len(hits))
    return hits[0]


def find_arrays(fw):
    """Read the tile-map and attribute-array addresses out of ShowLogo's code.

    ShowLogo is found by the shape of its descriptor use: it loads the window-0
    palette descriptor, then the 1 bpp bank, then the 2 bpp bank, i.e. three
    RAM addresses R+0x70, R+0xCC, R+0xC0 built close together.  That fixes both
    ShowLogo's location and R, which is not the same in every image.

    Registers are tracked as (value, complete).  Only a value finished off by
    an `or`/`add` counts as an address: in `lduh [%l1+%o5]` both operands hold
    something derived from a `sethi`, but only %l1 went through the `or` that
    adds %lo, the other is the loop index scaled from a bare `sethi`.
    """
    img = memoryview(fw)[MAIN:]
    n = len(img) // 4
    words = struct.unpack(">%dI" % n, img[:n * 4])

    regs, refs = {}, []
    for i, w in enumerate(words):
        if (w >> 30) == 0 and (w >> 22) & 7 == 4:
            regs[(w >> 25) & 31] = (w & 0x3FFFFF) << 10
        elif (w >> 30) == 2 and ((w >> 19) & 0x3F) in (0x00, 0x02) and (w >> 13) & 1:
            base = regs.get((w >> 14) & 31)
            if base is not None and RAM[0] <= base < RAM[1]:
                refs.append((i, base + sx13(w & 0x1FFF)))

    by_val = {}
    for i, v in refs:
        by_val.setdefault(v, []).append(i)
    rest = (D_FONT0_1BPP, D_FONT0_2BPP, D_PAL1, D_FONT1)
    anchors = [(i, v - D_PAL0) for i, v in refs
               if all(any(i < j < i + 140 for j in by_val.get(v + d - D_PAL0, ()))
                      for d in rest)]
    if len(anchors) != 1:
        raise SystemExit("ShowLogo: expected 1 candidate, got %d" % len(anchors))
    start, block_ram = anchors[0]

    regs, lduh, ldub = {}, [], []
    for i in range(start, min(start + 0x100, n)):
        w = words[i]
        op, rd, op3 = w >> 30, (w >> 25) & 31, (w >> 19) & 0x3F
        if op == 1:                                    # call clobbers %g and %o
            for r in list(regs):
                if r < 8 or 8 <= r < 16:
                    del regs[r]
            continue
        if op == 0:
            if (w >> 22) & 7 == 4:                     # sethi
                regs[rd] = ((w & 0x3FFFFF) << 10, False)
            continue
        if op == 2:                                    # or/add reg, simm13
            base = regs.get((w >> 14) & 31)
            regs[rd] = (base[0] + sx13(w & 0x1FFF), True) \
                if op3 in (0x00, 0x02) and (w >> 13) & 1 and base else None
            continue
        if op == 3:
            if not (w >> 13) & 1:                      # [reg + reg]
                for r in ((w >> 14) & 31, w & 31):
                    v = regs.get(r)
                    if v and v[1] and 0x10000 <= v[0] < 0x180000:
                        (lduh if op3 == 0x02 else ldub if op3 == 0x01 else []).append(v[0])
            regs[rd] = None

    maps = list(dict.fromkeys(lduh))
    attrs = list(dict.fromkeys(ldub))
    if len(maps) < 2 or not attrs:
        raise SystemExit("ShowLogo: found %d tile maps and %d attribute arrays"
                         % (len(maps), len(attrs)))
    return block_ram, maps[0], attrs[0], maps[1]


def rle_decode(src):
    """Runs of 0x00 and 0xFF carry a count byte; 0 means 256.  Other bytes are
    literals.  See FUN_000B8C54 in Leon2 Main."""
    out = bytearray()
    p = 0
    while p < len(src):
        v = src[p]
        if v in (0x00, 0xFF):
            cnt = src[p + 1] if p + 1 < len(src) else 0
            out += bytes([v]) * (cnt or 256)
            p += 2
        else:
            out.append(v)
            p += 1
    return bytes(out)


def bitstream(plane):
    """One 27-byte plane -> 216 pixel bits, top-left first.

    OSD RAM is addressed in **24-bit words** -- that is where the 0x678 gap
    between the two bank bases comes from: 184 tiles x 9 words.  A word holds
    two 12-pixel rows and is assembled from the byte stream **little-endian**,
    with the upper row in the low twelve bits.  Get either half of that wrong
    and the glyph edges fray: the wrong byte order shifts every second row by
    half a byte, the wrong row order transposes rows in pairs and turns clean
    diagonals into small combs.
    """
    out = []
    for k in range(0, len(plane), 3):
        w = plane[k] | plane[k + 1] << 8 | plane[k + 2] << 16
        out.append(format(w & 0xFFF, "012b"))
        out.append(format(w >> 12, "012b"))
    return "".join(out)


def tiles(blob, bpp):
    """Split a decoded bank into per-tile pixel-index grids.

    In the 2 bpp bank the first plane is the low bit, which puts "msi" on index
    1 and "MPG" on index 2.  Confirmed against a photograph of the boot screen:
    "msi" comes out white (palette entry 0xFFFF) and "MPG" magenta (0x0FE9).
    """
    per = BYTES_1BPP if bpp == 1 else BYTES_2BPP
    if len(blob) % per:
        raise SystemExit("tile bank: %d bytes is not a multiple of %d" % (len(blob), per))
    out = []
    for t in range(len(blob) // per):
        g = blob[t * per:(t + 1) * per]
        lo = bitstream(g[:BYTES_1BPP])
        hi = bitstream(g[BYTES_1BPP:]) if bpp == 2 else None
        out.append([[int(lo[y * TILE_W + x]) | (int(hi[y * TILE_W + x]) << 1 if hi else 0)
                     for x in range(TILE_W)] for y in range(TILE_H)])
    return out


def read_map(fw, addr, cells):
    return struct.unpack_from(">%dH" % cells, fw, addr + MAIN)


def palette(fw, off):
    """The uploaded palette as 16-bit entries.  A cell picks its colour with
    `attribute byte + pixel index`, so the attribute is a base into this table
    rather than a colour by itself: window 0 uses attributes 0 and 3, and
    entries 0 and 3 are both 0x0000, which is why the background stays black
    under either."""
    n, _, src = desc8(fw, off)
    return list(struct.unpack_from("<%dH" % (n // 2), fw, src + MAIN))


def paint(cols, rows, cell):
    """cell(col, row) -> tile grid or None; returns a pixel-index raster."""
    img = [[0] * (cols * TILE_W) for _ in range(rows * TILE_H)]
    for r in range(rows):
        for c in range(cols):
            g = cell(c, r)
            if g is None:
                continue
            for y in range(TILE_H):
                img[r * TILE_H + y][c * TILE_W:(c + 1) * TILE_W] = g[y]
    return img


def unpack(v):
    """Palette entry -> RGB.  Plain RGB565; the entries are read little-endian,
    the same convention the OSD uses for its 24-bit tile words, so the bytes
    `0f e9` in the image are the value 0xE90F and come out a bright magenta."""
    return ((v >> 11 & 0x1F) * 255 // 31, (v >> 5 & 0x3F) * 255 // 63,
            (v & 0x1F) * 255 // 31)


def write_png(path, img, pal):
    h, w = len(img), len(img[0])
    rgb = [bytes(unpack(e)) for e in pal]
    raw = bytearray()
    for row in img:
        raw.append(0)
        for v in row:
            raw += rgb[v]

    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c))

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)))
        # Tag the file sRGB.  Untagged PNGs are read as sRGB by some viewers and
        # as raw device values by others, and on a wide-gamut panel the two look
        # quite different -- which is exactly the kind of doubt this avoids.
        f.write(chunk(b"sRGB", b"\x00"))
        f.write(chunk(b"gAMA", struct.pack(">I", 45455)))
        f.write(chunk(b"cHRM", struct.pack(">8I", 31270, 32900, 64000, 33000,
                                           30000, 60000, 15000, 6000)))
        f.write(chunk(b"IDAT", zlib.compress(bytes(raw), 9)))
        f.write(chunk(b"IEND", b""))
    return w, h


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("firmware")
    ap.add_argument("-o", "--out", default="out/logo", help="output directory")
    args = ap.parse_args()

    fw = open(args.firmware, "rb").read()
    os.makedirs(args.out, exist_ok=True)

    block = find_descriptor_block(fw)
    block_ram, map0, attr_addr, map1 = find_arrays(fw)
    print("descriptor block  file %#08x  -> %#010x" % (block, block_ram))
    print("window 0  map %#08x  attr %#08x  %d x %d tiles" % (map0, attr_addr, COLS0, ROWS0))
    print("window 1  map %#08x                 %d x %d tiles" % (map1, COLS1, ROWS1))

    def bank(off, bpp):
        n, _, _, src = desc12(fw, block + off)
        blob = rle_decode(fw[src + MAIN:src + MAIN + n])
        t = tiles(blob, bpp)
        print("  bank @%#08x  %5d B RLE -> %5d B  = %3d tiles, %d bpp"
              % (src, n, len(blob), len(t), bpp))
        return t

    # ---- window 0: two banks, selected per cell by the attribute byte -------
    t2 = bank(D_FONT0_2BPP, 2)
    t1 = bank(D_FONT0_1BPP, 1)
    cells0 = COLS0 * ROWS0
    m0 = read_map(fw, map0, cells0)
    attr = fw[attr_addr + MAIN:attr_addr + MAIN + cells0]
    for a, t in ((0, t2), (3, t1)):
        used = {m0[i] for i in range(cells0) if attr[i] == a}
        if used and max(used) >= len(t):
            raise SystemExit("window 0 attr=%d: tile %d out of %d" % (a, max(used), len(t)))
        print("  attr=%d: %d cells, %d distinct tiles" % (a, sum(1 for x in attr if x == a), len(used)))

    def cell0(c, r):
        i = r * COLS0 + c
        t = t2 if attr[i] == 0 else t1
        if m0[i] >= len(t):
            return None
        return [[attr[i] + v for v in row] for row in t[m0[i]]]

    # ---- window 1: a single 1 bpp bank, attribute 0 --------------------------
    tb = bank(D_FONT1, 1)
    m1 = read_map(fw, map1, COLS1 * ROWS1)
    if max(m1) >= len(tb):
        raise SystemExit("window 1: tile %d out of %d" % (max(m1), len(tb)))

    def cell1(c, r):
        return tb[m1[r * COLS1 + c]]

    def cell1_drawn(c, r):
        return tb[0] if c <= BLANK1 else cell1(c, r)

    pal0, pal1 = palette(fw, block + D_PAL0), palette(fw, block + D_PAL1)
    for name, cols, rows, fn, pal in (
            ("logo_msi", COLS0, ROWS0, cell0, pal0),
            ("logo_badges", COLS1, ROWS1, cell1_drawn, pal1),
            ("logo_badges_hidden", COLS1, ROWS1, cell1, pal1)):
        path = os.path.join(args.out, name + ".png")
        print("%s: %d x %d px" % (path, *write_png(path, paint(cols, rows, fn), pal)))

    for name, pal in (("window 0", pal0), ("window 1", pal1)):
        print("palette %s: %s" % (name, "  ".join(
            "%d=%04X %s" % (i, e, "%02X%02X%02X" % unpack(e)) for i, e in enumerate(pal))))


if __name__ == "__main__":
    main()
