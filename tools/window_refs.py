#!/usr/bin/env python3
"""Сырой поиск статических адресов заданного AHB-диапазона во всех разделах образа MSI.

Сделан для проверки окна SRAM Leon2 Main `9F040000..9F05FFFF`
(`docs/leon2-main-image.md` §10), но диапазон задаётся ключами. Разделы
берутся из таблицы `0x6000`, источник раздела — `id << 16 | lo`.

По архитектурам:

* **8051** (загрузчик, `id=0x01/0x02`): 32-битная константа BE/LE по любому
  смещению — так ловятся инлайн-данные после `LCALL 0x09BD`; плюс
  `MOV Rn/A/dir,#9F`, за которым в пределах 12 байт стоит `#04/#05`.
  Адреса, собранные арифметикой (`ADDC A,#0x9F`), этим не ловятся — их
  нужно разбирать отдельно.
* **SPARC** (`id=0x05/0x0B/0x0D/0x10`): пары `sethi %hi` + `or/add/ld/st`
  с тем же регистром и выровненные BE-слова.
* **Xtensa LE** (`id=0x03`): LE-слова, выровненные и по любому смещению
  (литералы `L32R`).
* **Данные** (`id=0x0A/0x0E`) и всё вне разделов: BE/LE-слова.

Контрольные диапазоны (портал 0, портал 1, core-control Main) печатаются
рядом: пустой контроль значит, что приём не работает для этого образа.
Любое совпадение — кандидат, а не обращение: его надо разобрать листингом.
Отрицательный результат подтверждать в Ghidra (`RefsInRange.java`).

  .venv/bin/python tools/window_refs.py MSI_MPG_341CQPX_QD-OLED_FW.034_D728.bin
"""
import argparse
import struct

ARCH = {  # id -> (архитектура, CPU-база)
    0x01: ("8051", 0), 0x02: ("8051", 0),
    0x03: ("xtensa", 0x40000000),
    0x05: ("sparc", 0xA0060000), 0x0B: ("sparc", 0x9F1B0000),
    0x0D: ("sparc", 0xA0028000), 0x10: ("sparc", 0),
    0x0A: ("data", 0x9F196000), 0x0E: ("data", 0xA8024000),
}
BOOT = (0x0, 0x1900)  # первичный загрузчик 8051 в начале файла


def main():
    ap = argparse.ArgumentParser(description="Сырой поиск адресов AHB-диапазона в разделах образа MSI")
    ap.add_argument("firmware")
    ap.add_argument("--lo", type=lambda s: int(s, 16), default=0x9F040000)
    ap.add_argument("--hi", type=lambda s: int(s, 16), default=0x9F060000,
                    help="верхняя граница, не включительно")
    a = ap.parse_args()
    d = open(a.firmware, "rb").read()

    ranges = {
        "TARGET": (a.lo, a.hi),
        "MAIN-ALIAS": (0xA0028000, 0xA0048000),  # смысл только для образов Main
        "ctl-PORT0": (0x9F0A0100, 0x9F0A0200),
        "ctl-PORT1": (0x9F130000, 0x9F130200),
        "ctl-CORE": (0x9F020000, 0x9F030000),
    }

    def inr(v):
        return [k for k, (lo, hi) in ranges.items() if lo <= v < hi]

    def words(buf, base, fmt, step):
        out = {}
        for i in range(0, len(buf) - 3, step):
            v = struct.unpack(fmt, buf[i:i + 4])[0]
            for k in inr(v):
                out.setdefault(k, []).append((base + i, v))
        return out

    def sethi_pairs(buf, base):
        ws = [struct.unpack(">I", buf[i:i + 4])[0] for i in range(0, len(buf) - 3, 4)]
        out = {}
        for i, w in enumerate(ws):
            if w >> 30 != 0 or (w >> 22) & 7 != 4:
                continue
            rd, hi = (w >> 25) & 31, (w & 0x3FFFFF) << 10
            full = hi
            for x in ws[i + 1:i + 17]:
                if x >> 30 in (2, 3) and (x >> 13) & 1 and ((x >> 14) & 31) == rd:
                    s = x & 0x1FFF
                    full = (hi + (s - 0x2000 if s & 0x1000 else s)) & 0xFFFFFFFF
                    break
                if x >> 30 == 2 and ((x >> 25) & 31) == rd:
                    break
            for k in set(inr(hi)) | set(inr(full)):
                out.setdefault(k, []).append((base + 4 * i, full))
        return out

    def i8051(buf):
        out = {}
        for fmt, tag in ((">I", "be"), ("<I", "le")):
            for k, v in words(buf, 0, fmt, 1).items():
                out[f"{k}/{tag}"] = v
        for i in range(len(buf) - 2):
            op = buf[i]
            imm = buf[i + 1] if (0x78 <= op <= 0x7F or op == 0x74) else \
                buf[i + 2] if op == 0x75 else None
            if imm != 0x9F:
                continue
            for j in range(i + 2, min(i + 14, len(buf) - 1)):
                if (0x78 <= buf[j] <= 0x7F or buf[j] == 0x74) and buf[j + 1] in (4, 5):
                    out.setdefault("split-9F/04-05", []).append((i, 0))
                    break
        return out

    def show(name, res):
        print(f"== {name}")
        for k in sorted(res):
            v = res[k]
            print(f"  {k}: {len(v)}  " + " ".join(f"{p:X}={x:X}" for p, x in v[:16])
                  + (" …" if len(v) > 16 else ""))

    parts = [("boot", BOOT[0], BOOT[1], "8051", 0)]
    for o in range(0x6000, 0x6100, 8):
        _bank, pid, lo, size = struct.unpack(">BBHI", d[o:o + 8])
        if pid not in ARCH or size == 0:
            continue
        arch, base = ARCH[pid]
        parts.append((f"id{pid:02X}", (pid << 16) | lo, size, arch, base))

    covered = bytearray(d)
    for name, off, size, arch, base in parts:
        buf = d[off:off + size]
        covered[off:off + size] = bytes(size)
        print(f"# {name} {arch} file {off:06X}+{size:X} base {base:08X}")
        if arch == "8051":
            show(f"{name} bytes", i8051(buf))
        elif arch == "xtensa":
            show(f"{name} LE aligned", words(buf, base, "<I", 4))
            show(f"{name} LE any offset", words(buf, base, "<I", 1))
        elif arch == "sparc":
            show(f"{name} sethi pairs", sethi_pairs(buf, base))
            show(f"{name} BE aligned", words(buf, base, ">I", 4))
        else:
            show(f"{name} BE aligned", words(buf, base, ">I", 4))
    show("outside partitions BE any offset", words(bytes(covered), 0, ">I", 1))
    show("outside partitions LE any offset", words(bytes(covered), 0, "<I", 1))


if __name__ == "__main__":
    main()
