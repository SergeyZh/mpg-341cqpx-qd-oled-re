#!/usr/bin/env python3
"""Эталон tests/data/update-034.txt из захвата USBPcap штатного обновления.

Берутся HID-отчёты 4 моста (bus 1, dev 34): OUT на EP2 и IN на EP1 в исходном
порядке, остальные устройства шины отбрасываются. После записи эталон
декодируется обратно и сверяется с захватом.

    .venv/bin/python firmware/u7005/tools/make_update_fixture.py \\
        --capture captures/update-034/usb-04-update-034.pcapng
"""
import argparse
import hashlib
import sys
from pathlib import Path

from msi_reference import DATA, ROOT, decode_update, encode_update, fw034, packets_sha256

sys.path.insert(0, str(ROOT/'tools'))
from usbpcap_hid import packets as capture_packets  # noqa: E402


def bridge_reports(capture):
    for p in capture_packets(capture):
        if (p.bus, p.dev, p.xfer) != (1, 34, 1) or len(p.payload) != 64 or p.payload[0] != 4:
            continue
        if p.ep == 2 and p.out:
            yield True, p.payload
        elif p.ep == 0x81 and not p.out:
            yield False, p.payload


def main():
    parser = argparse.ArgumentParser(description='Эталон обновления FW.034 для тестов U7005.')
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=DATA/'update-034.txt')
    args = parser.parse_args()
    firmware = fw034()
    packets = list(bridge_reports(args.capture))
    source = hashlib.sha256(args.capture.read_bytes()).hexdigest()
    header = [
        '# HID-отчёты 4 моста U7005 при штатном обновлении FW.034, 2026-08-16.',
        f'# Источник: {args.capture.name}, SHA-256 {source}.',
        '# Строка — пакет: «>» хост→мост, «<» мост→хост. Токены: hex-байты,',
        '# «XX*N» — байт XX N раз, «@X» — курсор в файл FW.034 (hex), «=N» — N байт',
        '# файла от курсора, «xN» в конце — строка повторяется N раз.',
        '# Декодер: firmware/u7005/tools/msi_reference.py.',
        f'fw034-sha256: {hashlib.sha256(firmware).hexdigest()}',
        f'packets-sha256: {packets_sha256(packets)}',
        f'packets: {len(packets)}',
    ]
    text = '\n'.join(header + encode_update(packets, firmware)) + '\n'
    assert decode_update(text, firmware) == packets
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text)
    print(f'{args.output}: {len(packets)} пакетов, {len(text)} байт')


if __name__ == '__main__':
    main()
