#!/usr/bin/env python3
"""Узкая запись DDC/CI с macOS (Apple Silicon): только Video Black Level R/G/B.

Разрешены ровно VCP 0x6C (R), 0x6E (G), 0x70 (B) и значения 0..100 — штатные MCCS-коды,
которые Main FW.034 передаёт в смещения цветовой матрицы скалера
(docs/osd-menu-functions.md). Никаких других кодов VCP и сервисных опкодов скрипт не шлёт.
После SET выполняет штатный GET того же кода для сверки. Транспорт — tools/ddc_probe.py.

    .venv/bin/python tools/ddc_set_black_level.py 0x70 60
"""
import argparse
import sys
import time

import ddc_probe as dp

ALLOWED = {0x6C: "R", 0x6E: "G", 0x70: "B"}


def frame(body):
    chk = 0x6E ^ 0x51
    for b in body:
        chk ^= b
    return body + [chk]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("code", help="0x6C, 0x6E или 0x70")
    ap.add_argument("value", type=int, help="0..100")
    ap.add_argument("--service", type=lambda s: int(s, 0), default=None)
    ap.add_argument("--delay", type=float, default=0.1)
    a = ap.parse_args()
    vcp = int(a.code, 0)
    if vcp not in ALLOWED or not 0 <= a.value <= 100:
        sys.exit("разрешены только VCP 0x6C/0x6E/0x70 и значения 0..100")
    svc = dp.external_service(a.service)
    payload = frame([0x84, 0x03, vcp, (a.value >> 8) & 0xFF, a.value & 0xFF])
    print(f"→ 0x37 offset=0x51: {dp.hexs(payload)}   (DDC/CI SET VCP 0x{vcp:02x} = {a.value}, Black Level {ALLOWED[vcp]})")
    print(f"   write rc={dp.write_i2c(svc, 0x37, 0x51, payload)}")
    time.sleep(0.3)
    get = frame([0x82, 0x01, vcp])
    dp.write_i2c(svc, 0x37, 0x51, get)
    time.sleep(a.delay)
    rc, data = dp.read_i2c(svc, 0x37, 0x51, 12)
    print(f"← GET rc={rc}: {dp.hexs(data)}")
    if rc == 0 and len(data) >= 10 and data[0] == 0x6E and data[2] == 0x02:
        print(f"   vcp=0x{data[4]:02x} result={data[3]} max={(data[6] << 8) | data[7]} cur={(data[8] << 8) | data[9]}")


if __name__ == "__main__":
    main()
