#!/usr/bin/env python3
"""Короткая обратимая проба корпусного LED через уже открытый ISP.

Сначала: .venv/bin/python tools/isp_read.py --jedec [--bootloader]
Затем:   .venv/bin/python tools/led_indicator.py --sequence off white yellow
Без --sequence выполняется только чтение. Скалер остаётся в ISP.
Подробности и доказательства: docs/led-indicator.md.
"""

import argparse
from datetime import datetime, timezone
import time

from isp_read import Bridge

DATA, DIR, MASK = 0xF012, 0xF013, 0x0C
COLORS = {"off": 0x0C, "white": 0x08, "yellow": 0x04, "both": 0x00}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sequence", nargs="+", choices=COLORS)
    parser.add_argument("--seconds", type=float, default=3.0)
    args = parser.parse_args()
    if not 0.1 <= args.seconds <= 10:
        parser.error("--seconds должен быть в диапазоне 0.1…10")

    def report(message):
        print(f"{datetime.now(timezone.utc).isoformat()} {message}", flush=True)

    bridge = Bridge()
    original = None
    touched = False
    try:
        bridge.enter_bridge_only()
        chip = bridge.read_reg(0xD511)
        if chip != 0x17:
            raise RuntimeError(f"Неожиданный D511={chip:02X}, ожидался 17")
        original = bridge.read_reg(DATA)
        direction = bridge.read_reg(DIR)
        report(f"BASELINE D511={chip:02X} F012={original:02X} F013={direction:02X}")
        if not args.sequence:
            return
        if direction & MASK:
            raise RuntimeError("GPIO 7.2/7.3 не настроены как выходы; проба отменена")

        def set_bits(bits, label):
            current = bridge.read_reg(DATA)
            current_dir = bridge.read_reg(DIR)
            if current_dir != direction:
                raise RuntimeError("DIR изменился во время пробы")
            # DATA reads pad levels. Release input latches exactly as MSI's HAL.
            value = ((current | direction) & ~MASK) | bits
            bridge.write_reg(DATA, value)
            actual = bridge.read_reg(DATA)
            report(f"{label} write F012={value:02X}, read={actual:02X}")
            if (actual ^ value) & (~direction & 0xFF):
                raise RuntimeError("Read-back выходных битов не совпал")
            if (actual ^ original) & ~(direction | MASK) & 0xFF:
                raise RuntimeError("Изменился выход вне LED-маски")

        for color in args.sequence:
            touched = True
            set_bits(COLORS[color], color.upper())
            time.sleep(args.seconds)
            set_bits(original & MASK, "RESTORE")
            time.sleep(1)
    finally:
        try:
            if touched and original is not None:
                # Restore only the LED bits, preserving all other current pads.
                current = bridge.read_reg(DATA)
                direction = bridge.read_reg(DIR)
                value = ((current | direction) & ~MASK) | (original & MASK)
                bridge.write_reg(DATA, value)
                actual = bridge.read_reg(DATA)
                report(f"FINAL RESTORE F012={actual:02X} F013={direction:02X}")
                if (actual ^ original) & MASK:
                    raise RuntimeError("LED не восстановлен; требуется аппаратный reset")
        finally:
            bridge.exit()
            bridge.dev.close()


if __name__ == "__main__":
    main()
