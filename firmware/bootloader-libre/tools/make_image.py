#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Create a firmware copy with the libre bootloader overlaid at offset zero."""

from __future__ import annotations

import argparse
from pathlib import Path


MAX_BOOTLOADER_SIZE = 0x4000
SECTOR_SIZE = 0x1000


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bootloader", type=Path, required=True)
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    bootloader = args.bootloader.read_bytes()
    firmware = bytearray(args.firmware.read_bytes())
    if (not bootloader or len(bootloader) > MAX_BOOTLOADER_SIZE or
            len(bootloader) % SECTOR_SIZE != 0):
        raise SystemExit(
            "bootloader length must be a non-zero multiple of 0x1000 and at most 0x4000"
        )
    if len(firmware) < 0x8000:
        raise SystemExit("firmware is too short to contain the boot area")

    firmware[:len(bootloader)] = bootloader
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(firmware)
    print(f"wrote {args.output} ({len(firmware)} bytes)")


if __name__ == "__main__":
    main()
