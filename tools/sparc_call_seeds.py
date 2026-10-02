#!/usr/bin/env python3
"""Список точек входа для SeedFunctions.java: цели прямых SPARC `call` с прологом `save %sp`.

Анализатор Ghidra доходит не до всех функций Leon2 Main (в runtime-main-034 не было
EF814/EFADC), и тогда RefsTo/CallReach дают ложные «нет». Сырой проход по образу
собирает цели всех слов вида `call disp30`, которые попадают внутрь образа и начинаются
с `save %sp, -N, %sp`. Ложные call-слова из данных этим фильтром почти отсекаются;
листовые функции без `save` не попадают — их добавляют вручную через --extra.
"""
import argparse
import struct

SAVE_MASK, SAVE_SP = 0xFFFFE000, 0x9DE3A000  # save %sp, simm13<0, %sp


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("firmware", help="полный образ FW.bin")
    ap.add_argument("--offset", type=lambda s: int(s, 0), default=0x108000,
                    help="файловое смещение адреса 0 образа (Leon2 Main: 0x108000)")
    ap.add_argument("--size", type=lambda s: int(s, 0), default=0x160000,
                    help="сколько байт образа просматривать")
    ap.add_argument("--extra", default="", help="доп. адреса через запятую (листовые функции)")
    ap.add_argument("-o", "--output", required=True)
    a = ap.parse_args()

    data = open(a.firmware, "rb").read()[a.offset:a.offset + a.size]
    words = struct.unpack(">%dI" % (len(data) // 4), data[:len(data) // 4 * 4])
    seeds = set()
    for i, w in enumerate(words):
        if w >> 30 != 1:
            continue
        disp = w & 0x3FFFFFFF
        if disp & 0x20000000:
            disp -= 0x40000000
        t = i * 4 + disp * 4
        if 0 <= t < len(words) * 4 and words[t // 4] & SAVE_MASK == SAVE_SP:
            seeds.add(t)
    seeds.update(int(x, 16) for x in a.extra.split(",") if x.strip())
    with open(a.output, "w") as f:
        for t in sorted(seeds):
            f.write("0x%x\n" % t)
    print("%d точек входа -> %s" % (len(seeds), a.output))


if __name__ == "__main__":
    main()
