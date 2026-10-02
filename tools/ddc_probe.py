#!/usr/bin/env python3
"""Пробник DDC/I2C монитора с macOS (Apple Silicon).

Отвечает на открытый вопрос №8 из docs/nt68503-i2c-service-protocol.md:
доступен ли сырой сервисный слейв скалера (`0x6E`/`0x6F`, он же 7-битный 0x37)
с видеолинка, без предварительного `UartSetI2CEnable` через мост U7005.

Работает через приватный IOKit API `IOAVService*` — тот же, которым пользуются
m1ddc и BetterDisplay. Только Apple Silicon; на Intel-маках нужен IOFramebufferI2C.

ТОЛЬКО ЧТЕНИЕ. Наружу уходят ровно два вида посылок:
  * штатный DDC/CI GET VCP (`82 01 <vcp>`) — контрольный опыт;
  * сырой `03 87 hi lo` — чтение регистра скалера (docs/nt68503-i2c-service-protocol.md).
Опкоды записи (`0x78`), запуска SPI (`0x25`, `0x53`) и весь ISP-план слейва `0xB0`
не реализованы намеренно.

    .venv/bin/python tools/ddc_probe.py list
    .venv/bin/python tools/ddc_probe.py vcp 0x10
    .venv/bin/python tools/ddc_probe.py raw 0xF0C0
"""

import argparse
import ctypes
import sys
import time

IOKIT = "/System/Library/Frameworks/IOKit.framework/IOKit"
CF = "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"

iokit = ctypes.CDLL(IOKIT)
cf = ctypes.CDLL(CF)

cf.CFStringCreateWithCString.restype = ctypes.c_void_p
cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
cf.CFStringGetCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]
cf.CFRelease.argtypes = [ctypes.c_void_p]

iokit.IOServiceMatching.restype = ctypes.c_void_p
iokit.IOServiceMatching.argtypes = [ctypes.c_char_p]
iokit.IOServiceGetMatchingServices.argtypes = [ctypes.c_uint32, ctypes.c_void_p,
                                               ctypes.POINTER(ctypes.c_uint32)]
iokit.IOIteratorNext.restype = ctypes.c_uint32
iokit.IOIteratorNext.argtypes = [ctypes.c_uint32]
iokit.IORegistryEntryCreateCFProperty.restype = ctypes.c_void_p
iokit.IORegistryEntryCreateCFProperty.argtypes = [ctypes.c_uint32, ctypes.c_void_p,
                                                  ctypes.c_void_p, ctypes.c_uint32]

for name in ("IOAVServiceCreateWithService", "IOAVServiceReadI2C", "IOAVServiceWriteI2C"):
    if not hasattr(iokit, name):
        sys.exit(f"в IOKit нет {name} — этот путь доступен только на Apple Silicon")

iokit.IOAVServiceCreateWithService.restype = ctypes.c_void_p
iokit.IOAVServiceCreateWithService.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
iokit.IOAVServiceReadI2C.restype = ctypes.c_int
iokit.IOAVServiceReadI2C.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32,
                                     ctypes.c_void_p, ctypes.c_uint32]
iokit.IOAVServiceWriteI2C.restype = ctypes.c_int
iokit.IOAVServiceWriteI2C.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32,
                                      ctypes.c_void_p, ctypes.c_uint32]

KCFSTRING_UTF8 = 0x08000100


def cfstr(s):
    return cf.CFStringCreateWithCString(None, s.encode(), KCFSTRING_UTF8)


def cfstr_value(ref):
    if not ref:
        return None
    buf = ctypes.create_string_buffer(256)
    if cf.CFStringGetCString(ref, buf, 256, KCFSTRING_UTF8):
        return buf.value.decode()
    return None


def av_services():
    """Все DCPAVServiceProxy с их Location."""
    out = []
    it = ctypes.c_uint32(0)
    matching = iokit.IOServiceMatching(b"DCPAVServiceProxy")
    if iokit.IOServiceGetMatchingServices(0, matching, ctypes.byref(it)) != 0:
        return out
    key = cfstr("Location")
    while True:
        entry = iokit.IOIteratorNext(it)
        if not entry:
            break
        prop = iokit.IORegistryEntryCreateCFProperty(entry, key, None, 0)
        loc = cfstr_value(prop)
        if prop:
            cf.CFRelease(prop)
        out.append((entry, loc))
    cf.CFRelease(key)
    return out


def external_services():
    out = []
    for entry, loc in av_services():
        if loc == "External":
            svc = iokit.IOAVServiceCreateWithService(None, entry)
            if svc:
                out.append((entry, svc))
    return out


def external_service(want=None):
    """Внешних сервисов бывает несколько (док, стойка портов), и живой из них
    не обязательно первый. Отбираем тем, что читаем EDID: адрес 0x50 отвечает
    у любого монитора, а операция пассивная."""
    found = external_services()
    if not found:
        sys.exit("внешний DCPAVServiceProxy не найден или IOAVService не создался")
    if want is not None:
        for entry, svc in found:
            if entry == want:
                return svc
        sys.exit(f"сервис 0x{want:x} не найден среди внешних")
    if len(found) == 1:
        return found[0][1]
    # EDID отдают и мёртвые линки (например монитор, висящий на доке через
    # MST-хаб), поэтому решает не он, а живой канал по адресу 0x37.
    for entry, svc in found:
        rc, _ = read_i2c(svc, 0x37, 0x51, 4)
        if rc == 0:
            rc_e, edid = read_i2c(svc, 0x50, 0x00, 24)
            note = f", EDID v1.{edid[19]}" if rc_e == 0 else ""
            print(f"   (выбран сервис 0x{entry:x}: канал 0x37 отвечает{note})")
            return svc
    print("   (ни один внешний сервис не ответил по 0x37, беру первый)")
    return found[0][1]


def hexs(b):
    return " ".join(f"{x:02x}" for x in b)


def write_i2c(svc, chip, offset, payload):
    buf = (ctypes.c_ubyte * len(payload))(*payload)
    rc = iokit.IOAVServiceWriteI2C(svc, chip, offset, buf, len(payload))
    return rc


def read_i2c(svc, chip, offset, length):
    buf = (ctypes.c_ubyte * length)()
    rc = iokit.IOAVServiceReadI2C(svc, chip, offset, buf, length)
    return rc, bytes(buf)


def cmd_list(args):
    services = av_services()
    if not services:
        print("DCPAVServiceProxy не найден")
        return
    for entry, loc in services:
        note = ""
        if loc == "External":
            svc = iokit.IOAVServiceCreateWithService(None, entry)
            if svc:
                rc, data = read_i2c(svc, 0x50, 0x00, 8)
                note = (" EDID: " + hexs(data)) if rc == 0 else f" EDID rc={rc & 0xffffffff:#x}"
        print(f"io_object 0x{entry:x}  Location={loc}{note}")


def cmd_edid(args):
    """Контрольный опыт без всякой записи: чтение EDID по адресу 0x50."""
    svc = external_service(args.service)
    rc, data = read_i2c(svc, 0x50, args.offset, args.read_len)
    print(f"← 0x50 offset=0x{args.offset:02x} rc={rc & 0xffffffff:#x}: {hexs(data)}")
    if rc == 0 and data[:8] == b"\x00\xff\xff\xff\xff\xff\xff\x00":
        print("   заголовок EDID на месте — I2C до монитора работает")


def cmd_vcp(args):
    """Контрольный опыт: штатный DDC/CI GET. Если он не работает, любой
    отрицательный результат сырого опыта ничего не значит."""
    vcp = int(args.code, 0)
    svc = external_service(args.service)
    frame = [0x82, 0x01, vcp]
    chk = 0x6E ^ 0x51
    for b in frame:
        chk ^= b
    payload = frame + [chk]
    print(f"→ 0x37 offset=0x51: {hexs(payload)}   (DDC/CI GET VCP 0x{vcp:02x})")
    rc = write_i2c(svc, 0x37, 0x51, payload)
    print(f"   write rc={rc}")
    time.sleep(args.delay)
    rc, data = read_i2c(svc, 0x37, args.read_offset, args.read_len)
    print(f"← rc={rc}: {hexs(data)}")
    # 6E 88 02 <result> <vcp> <type> <max_hi> <max_lo> <cur_hi> <cur_lo> <xor>
    if rc == 0 and len(data) >= 10 and data[0] == 0x6E and data[2] == 0x02:
        mx = (data[6] << 8) | data[7]
        cur = (data[8] << 8) | data[9]
        print(f"   штатный ответ DDC/CI: vcp=0x{data[4]:02x} result={data[3]} "
              f"max={mx} cur={cur}")


def cmd_raw(args):
    """Сырой сервисный протокол скалера: 03 87 hi lo xor → 0x6E, ответ с 0x6F."""
    addr = int(args.reg, 0)
    if not 0 <= addr <= 0xFFFF:
        sys.exit("адрес регистра — 16 бит")
    chip = int(args.chip, 0)
    svc = external_service(args.service)
    hi, lo = addr >> 8, addr & 0xFF
    body = [0x03, 0x87, hi, lo]
    chk = (chip << 1)
    for b in body:
        chk ^= b
    payload = body + [chk]
    print(f"→ 0x{chip:02x} (write {chip << 1:#04x}): {hexs(payload)}"
          f"   (сырой 0x87: прочитать регистр 0x{addr:04X})")
    # первый байт посылки уходит параметром offset, остальные — буфером
    rc = write_i2c(svc, chip, payload[0], payload[1:])
    print(f"   write rc={rc}")
    time.sleep(args.delay)
    rc, data = read_i2c(svc, chip, args.read_offset, args.read_len)
    print(f"← rc={rc}: {hexs(data)}")
    if rc != 0:
        return
    if not any(data):
        print("   пусто — слейв не ответил (или API вернул нули)")
        return
    # ожидаемый ответ: [N] [0x78] [value] [xor], xor = XOR(read_addr, N, 0x78, value)
    for off in range(0, max(1, len(data) - 3)):
        n, op = data[off], data[off + 1]
        if op != 0x78:
            continue
        end = off + 1 + n
        if end >= len(data):
            continue
        x = (chip << 1) | 1
        for b in data[off:end]:
            x ^= b
        ok = "СХОДИТСЯ" if x == data[end] else f"не сходится (ждали {x:02x})"
        print(f"   кадр по смещению {off}: N={n} opcode=0x78 данные="
              f"{hexs(data[off + 2:end])} xor={data[end]:02x} — {ok}")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--delay", type=float, default=0.05, help="пауза между write и read, с")
    p.add_argument("--read-offset", type=lambda s: int(s, 0), default=0x51,
                   help="байт, который API пишет перед чтением (по умолчанию 0x51)")
    p.add_argument("--read-len", type=lambda s: int(s, 0), default=12)
    p.add_argument("--service", type=lambda s: int(s, 0), default=None,
                   help="io_object конкретного DCPAVServiceProxy (см. list)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="перечислить DCPAVServiceProxy")

    e = sub.add_parser("edid", help="контрольный опыт: чтение EDID по адресу 0x50")
    e.add_argument("--offset", type=lambda s: int(s, 0), default=0x00)

    v = sub.add_parser("vcp", help="контрольный опыт: штатный DDC/CI GET")
    v.add_argument("code", help="код VCP, например 0x10 (яркость)")

    r = sub.add_parser("raw", help="сырое чтение регистра скалера опкодом 0x87")
    r.add_argument("reg", help="16-битный адрес регистра, например 0xF0C0")
    r.add_argument("--chip", default="0x37",
                   help="7-битный адрес слейва: 0x37 = 0x6E/0x6F, 0x58 = 0xB0/0xB1")

    args = p.parse_args()
    {"list": cmd_list, "edid": cmd_edid, "vcp": cmd_vcp, "raw": cmd_raw}[args.cmd](args)


if __name__ == "__main__":
    main()
