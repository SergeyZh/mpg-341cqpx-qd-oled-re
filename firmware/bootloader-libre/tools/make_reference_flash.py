#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Rebuild the first 64 KiB of the monitor's U4002 bank 0 for `make verify`.

The MSI FW.034 file plus reference/u4002-slot1-table.txt (the 0x6FFF marker
and the slot-1 partition table, written by MSI's updater on the monitor and
absent from MSI files) equals the first 64 KiB of the dump byte for byte.
Both the input file and the result are checked against fixed SHA-256 values.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

FW034_SHA256 = "a3c033105dc044fcf7f560cdb03145c8a4ef64c6220f44bab1bebf1cb3a1965d"
# SHA-256 of flash/u4002_a.bin[:0x10000], the 2026-08-16 dump.
RESULT_SHA256 = "e8464a0e0094c9b85a3b8188d437a4e68f7c19535c563180a18870a397abc4c2"
SIZE = 0x10000


def parse_table(text: str) -> dict[int, int]:
    patch = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        address, _, data = line.partition(":")
        for offset, value in enumerate(bytes.fromhex(data)):
            patch[int(address, 16) + offset] = value
    return patch


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild U4002 bank 0 (64 KiB) from FW.034.")
    parser.add_argument("--fw034", type=Path, required=True)
    parser.add_argument("--table", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    firmware = args.fw034.read_bytes()
    actual = hashlib.sha256(firmware).hexdigest()
    if actual != FW034_SHA256:
        raise SystemExit(f"{args.fw034}: SHA-256 {actual}, expected FW.034 {FW034_SHA256}")
    image = bytearray(firmware[:SIZE])
    for address, value in parse_table(args.table.read_text()).items():
        image[address] = value
    actual = hashlib.sha256(image).hexdigest()
    if actual != RESULT_SHA256:
        raise SystemExit(f"rebuilt bank 0 SHA-256 {actual}, expected {RESULT_SHA256}")
    args.output.write_bytes(image)


if __name__ == "__main__":
    main()
