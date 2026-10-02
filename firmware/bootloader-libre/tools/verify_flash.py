#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Verify an ISP read-back and prove that only bootloader-a's sectors changed."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


SECTOR_SIZE = 0x1000
CAPTURE_SIZE = 0x4000


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bootloader", type=Path, required=True)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    args = parser.parse_args()

    bootloader = args.bootloader.read_bytes()
    before = args.before.read_bytes()
    after = args.after.read_bytes()

    if (not bootloader or len(bootloader) > CAPTURE_SIZE or
            len(bootloader) % SECTOR_SIZE != 0):
        raise SystemExit(
            f"{args.bootloader}: length {len(bootloader):#x}, expected a non-zero "
            f"multiple of {SECTOR_SIZE:#x} up to {CAPTURE_SIZE:#x}"
        )
    for path, data in ((args.before, before), (args.after, after)):
        if len(data) != CAPTURE_SIZE:
            raise SystemExit(
                f"{path}: length {len(data):#x}, expected {CAPTURE_SIZE:#x}"
            )
    target_size = len(bootloader)
    if after[:target_size] != bootloader:
        raise SystemExit(
            f"read-back of 0x0000..{target_size - 1:#06x} differs from bootloader-a"
        )
    if after[target_size:] != before[target_size:]:
        raise SystemExit(
            f"untargeted range {target_size:#06x}..0x3FFF changed"
        )

    print(f"target 0x0000..{target_size - 1:#06x}: MATCH")
    print(f"untouched {target_size:#06x}..0x3FFF: MATCH")
    print(f"before SHA-256: {sha256(before)}")
    print(f"after  SHA-256: {sha256(after)}")
    print(f"target SHA-256: {sha256(bootloader)}")


if __name__ == "__main__":
    main()
