#!/usr/bin/env python3
"""Собрать разреженный HEX; не заполнять защищённые страницы байтами FF."""
import argparse
import hashlib
import json
import struct
from pathlib import Path


def disk_image():
    disk = bytearray(44 * 512)
    boot = bytearray(512)
    boot[:11] = b'\xeb\x3c\x90U7005   '
    struct.pack_into('<HBHBHHBHHHII', boot, 11, 512, 1, 1, 2, 16, 44, 0xf8, 1, 1, 1, 0, 0)
    boot[36:62] = b'\x80\0\x29' + struct.pack('<I', 0x55373035) + b'MSI DRIVER ' + b'FAT12   '
    boot[510:512] = b'\x55\xaa'
    disk[:512] = boot
    # 1 boot, 2 FATs, 1 root directory; cluster 2 contains the driver URL.
    for sector in (1, 2):
        disk[sector*512:sector*512+5] = b'\xf8\xff\xff\xff\x0f'
    content = b'[InternetShortcut]\r\nURL=https://www.msi.com/support\r\n'
    entry = bytearray(32)
    entry[:11] = b'MSI     URL'
    entry[11] = 0x20
    struct.pack_into('<H', entry, 26, 2)
    struct.pack_into('<I', entry, 28, len(content))
    disk[1536:1568] = entry
    disk[2048:2048+len(content)] = content
    return bytes(disk)


def hex_record(address, kind, data):
    raw = bytes([len(data)]) + address.to_bytes(2, 'big') + bytes([kind]) + data
    return ':' + (raw + bytes([-sum(raw) & 255])).hex().upper() + '\n'


def intel_hex(segments):
    out, upper = [], None
    for base, data in segments:
        for offset in range(0, len(data), 16):
            address = base + offset
            if address >> 16 != upper:
                upper = address >> 16
                out.append(hex_record(0, 4, upper.to_bytes(2, 'big')))
            out.append(hex_record(address & 65535, 0, data[offset:offset+16]))
    out.append(hex_record(0, 1, b''))
    return ''.join(out)


def package(code):
    code += b'\xff' * (-len(code) % 4)
    if not 192 <= len(code) <= 0x10000:
        raise ValueError('Code must fit 0x00000..0x0FFFF')
    stack, reset = struct.unpack_from('<II', code)
    if stack != 0x20005000 or not reset & 1 or not 192 <= (reset & ~1) < len(code):
        raise ValueError('Invalid Cortex-M0 vectors')
    checksum = sum(code) & 65535
    segments = [(0, code), (0x10000, disk_image()), (0x1f7f8, struct.pack('<II', len(code), checksum))]
    manifest = {
        'format': 'u7005-source-v1', 'hardware_tested': False,
        'code_length': len(code), 'ldrom_checksum': checksum,
        'segments': [{'address': a, 'length': len(d), 'sha256': hashlib.sha256(d).hexdigest()}
                     for a, d in segments],
        'preserve': ['0x1E800..0x1EFFF USB mode', '0x1F800..0x1FFFF DataFlash',
                     'LDROM', 'CONFIG', 'SPROM'],
    }
    return segments, manifest


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('code', type=Path)
    ap.add_argument('-o', '--output', type=Path, required=True)
    args = ap.parse_args()
    segments, manifest = package(args.code.read_bytes())
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/'u7005.hex').write_text(intel_hex(segments))
    (args.output/'u7005-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    (args.output/'u7005-disk.bin').write_bytes(segments[1][1])
    print(f"HEX: code {manifest['code_length']} bytes, checksum {manifest['ldrom_checksum']:04X}; hardware untested")


if __name__ == '__main__':
    main()
