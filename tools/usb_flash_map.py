#!/usr/bin/env python3
"""Read-only extraction of USB AUX constants; see docs/usb-flash-bootloader.md.

This is not an 8051 emulator or a hardware test. Instruction semantics come from
the repaired Ghidra listing; this verifies the underlying bytes independently.
"""
import argparse
import hashlib
from pathlib import Path

SIZE = 0xE552
SHA256 = "bed2d9922e6e98990573dee3066d5871806e4ecd703a48d184c2135be128e592"


def startup_records(b):
    """Subset of Keil initialization used by this exact image (CODE:D46D)."""
    p = 0xC36D
    while b[p]:
        site = p
        op = b[p]
        p += 1
        count = op & 0x3F
        if count & 0x20:
            count = ((count & 0x1F) << 8) | b[p]
            p += 1
        if op & 0xC0 == 0x40:
            addr = int.from_bytes(b[p:p+2], "big")
            p += 2
            data = b[p:p+count]
            p += count
            yield site, "XDATA", addr, data
        elif op & 0xC0 == 0xC0:
            # Encoded bit address: high bit is the value, low seven the address.
            for encoded in b[p:p+count]:
                yield site, "BIT", encoded & 0x7F, bytes([encoded >> 7])
            p += count
        else:
            raise ValueError(f"Unexpected startup record {op:02x} at {site:04x}")
    if p != 0xC44D:
        raise ValueError(f"Unexpected startup terminator {p:04x}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--offset", type=lambda x: int(x, 0), default=0x20000,
                        help="AUX offset: 0x20000 in FW, 0 in extracted AUX, 0x1020000 in factory dump")
    args = parser.parse_args()
    with args.image.open("rb") as stream:
        stream.seek(args.offset)
        b = stream.read(SIZE)
    digest = hashlib.sha256(b).hexdigest()
    print(f"{args.image}: offset=0x{args.offset:x} size={len(b)} SHA256={digest}")
    if len(b) != SIZE or digest != SHA256:
        parser.error("Not the verified FW.023/.034/.037 USB AUX image; refusing address-based interpretation")
    ram = {}
    print("\nKeil startup records (CODE address, destination, bytes):")
    for site, kind, addr, data in startup_records(b):
        print(f"{site:04X} {kind}:{addr:04X} [{len(data)}] {data.hex(' ')}")
        if kind == "XDATA":
            ram.update((addr+i, value) for i, value in enumerate(data))
    assert ram[0x9C6] == ram[0x9CD] == 2
    assert bytes(ram[x] for x in range(0x8C9, 0x8CD)) == bytes(4)
    print("\nHost init (CODE address, operation/offset, value, delay argument):")
    p = 0xC9D2
    while b[p:p+2] != b"\xff\xff":
        op = int.from_bytes(b[p:p+2], "big")
        value = int.from_bytes(b[p+2:p+6], "big")
        print(f"{p:04X} {['write', 'set', 'clear'][op >> 12]:5} {op & 0x1FF:03X} {value:08X} {b[p+6]}")
        p += 7
    assert p == 0xCA3B
    print("\nControl request templates (XDATA address, on-wire bytes):")
    for addr in range(0x7D9, 0x801, 8):
        print(f"{addr:04X}: {bytes(ram[x] for x in range(addr, addr+8)).hex(' ')}")
    # DB76 comparisons in the order executed. ABCE(order=0) reverses each word.
    compare = [(0x914, 'N'), (0x913, 'V'), (0x912, 'T'), (0x919, 'S'),
               (0x918, 'C'), (0x917, '_'), (0x916, 'I'), (0x91D, 'M'), (0x91C, 'G')]
    wire = [((addr - 0x912) ^ 3, char) for addr, char in compare]
    assert [offset for offset, _ in wire] == list(range(1, 10))
    print("\nDB76 signature: file offsets", wire)
    # Counterexample to treating CheckSum Fail as an integrity check:
    # SETB bit00; LCALL A547; MOV C,bit00; RET. A547 -> DB76 false -> RET.
    assert b[0x9F87:0x9F8F] == bytes.fromhex("d2 00 12 a5 47 a2 00 22")
    assert b[0xA547:0xA54F] == bytes.fromhex("12 db 76 40 03 02 a6 f9")
    assert b[0xA6F9] == 0x22
    print("Verified: missing signature skips header parsing, not the caller's success flag.")
    print("Static extraction passed; no USB transaction was performed.")


if __name__ == "__main__":
    main()
