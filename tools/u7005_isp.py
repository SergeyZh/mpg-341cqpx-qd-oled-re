#!/usr/bin/env python3
"""USB ISP U7005, проверенный LDROM 0x15. См. docs/u7005-ldrom.md.

info: сведения приложения; probe: A0 → читающие ISP-команды → AB → приложение.
Трасса содержит исходные USB-отчёты. Команды обновления в probe не посылаются.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import struct
import time

APP = (0x1462, 0x3FA4)
ISP = (0x0416, 0x3F00)
PDID = 0x01205206
CONFIG = (0xFFFFFB7E, 0x1F800)


class Trace:
    def __init__(self, directory):
        directory.mkdir(parents=True, exist_ok=False)
        self.directory = directory
        self.file = (directory / 'usb.jsonl').open('x')

    def event(self, **data):
        self.file.write(json.dumps({'utc': datetime.now(timezone.utc).isoformat(), **data}) + '\n')
        self.file.flush()

    def result(self, data):
        (self.directory / 'result.json').write_text(json.dumps(data, indent=2) + '\n')


def open_device(ids, timeout=10):
    import hid
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        devices = hid.enumerate(*ids)
        if len(devices) > 1:
            raise RuntimeError(f'неоднозначное устройство {ids}: {len(devices)} HID-интерфейсов')
        if devices:
            dev = hid.device()
            try:
                dev.open_path(devices[0]['path'])
                dev.set_nonblocking(0)
                return dev
            except OSError as exc:
                last_error = exc
                dev.close()
        time.sleep(0.1)
    raise TimeoutError(f'нет доступного HID {ids[0]:04x}:{ids[1]:04x}: {last_error}')


def app_command(dev, command, trace):
    if command not in (0xB0, 0xB2, 0xB4, 0xA0):
        raise ValueError('разрешены только сведения приложения и переход в LDROM')
    packet = bytes((1, command)) + bytes(62)
    trace.event(mode='app', direction='out', packet=packet.hex())
    if dev.write(packet) != len(packet):
        raise IOError('неполная запись HID')
    if command == 0xA0:
        return None
    for _ in range(10):
        reply = bytes(dev.read(64, timeout_ms=300))
        trace.event(mode='app', direction='in', packet=reply.hex())
        if len(reply) >= 15 and reply[:2] == b'\x01\x5a':
            return reply[1:]
    raise TimeoutError(f'нет ответа приложения на {command:02x}')


def app_info(dev, trace):
    version = app_command(dev, 0xB0, trace)
    chip = app_command(dev, 0xB2, trace)
    board = app_command(dev, 0xB4, trace)
    result = {'app_version': version[1], 'ldrom_version': version[3],
              'ldrom_checksum': int.from_bytes(version[4:8], 'big'),
              'aprom_checksum': int.from_bytes(version[8:12], 'big'),
              'pdid': int.from_bytes(chip[1:5], 'big'),
              'board_id': int.from_bytes(board[1:5], 'little')}
    if result['pdid'] != PDID or result['ldrom_version'] != 0x15 or result['ldrom_checksum'] != 0xD926:
        raise RuntimeError(f'прошивка/микросхема не совпала с разобранным U7005: {result}')
    return result


class Loader:
    def __init__(self, dev, trace):
        self.dev, self.trace, self.sequence = dev, trace, 1

    def command(self, opcode, data=b'', *, reset=False):
        if opcode not in (0xAE, 0xA6, 0xB1, 0xA2, 0xCA, 0xA4, 0xAB):
            raise ValueError('команда отсутствует в списке разрешённых')
        if reset != (opcode == 0xAB):
            raise ValueError('возврат AB должен выполняться без ожидания ответа')
        if len(data) > 56:
            raise ValueError('слишком длинная команда')
        if opcode == 0xAE:
            self.sequence = 1
        if opcode == 0xA4:
            self.sequence = struct.unpack('<I', data)[0]
        return self._exchange(opcode, data, reset=reset)

    def _exchange(self, opcode, data=b'', *, reset=False, timeout_ms=5000):
        if len(data) > 56:
            raise ValueError('слишком длинная команда')
        packet = (struct.pack('<II', opcode, self.sequence) + data).ljust(64, b'\0')
        self.trace.event(mode='isp', direction='out', packet=packet.hex())
        # HID-дескриптор LDROM не имеет Report ID; hidapi требует ведущий ноль.
        if self.dev.write(b'\0' + packet) != 65:
            raise IOError('неполная запись ISP HID')
        if reset:
            return None
        reply = bytes(self.dev.read(64, timeout_ms=timeout_ms))
        self.trace.event(mode='isp', direction='in', packet=reply.hex())
        if len(reply) != 64:
            raise IOError(f'ожидалось 64 байта, получено {len(reply)}')
        checksum = struct.unpack_from('<H', reply)[0]
        sequence = struct.unpack_from('<I', reply, 4)[0]
        if checksum != sum(packet) & 0xFFFF or sequence != self.sequence + 1:
            raise IOError(f'не совпал checksum/sequence: {checksum:04x}, {sequence}')
        self.sequence += 2
        return reply

    def inspect(self):
        self.command(0xAE)
        version = self.command(0xA6)[8]
        chip = struct.unpack_from('<I', self.command(0xB1), 8)[0]
        config = struct.unpack_from('<II', self.command(0xA2), 8)
        boot = struct.unpack_from('<I', self.command(0xCA), 8)[0]
        self.command(0xA4, struct.pack('<I', 101))
        if struct.unpack_from('<II', self.command(0xA2), 8) != config:
            raise IOError('CONFIG изменился между двумя чтениями')
        if version != 0x15 or chip != PDID or config != CONFIG or boot != 2:
            raise RuntimeError(f'неожиданный ISP: {version:x}, {chip:x}, {config}, {boot}')
        return {'version': version, 'pdid': chip, 'config': config, 'boot_source': boot}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('info', 'probe'))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    trace = Trace(args.out)
    result = {'complete': False}
    try:
        dev = open_device(APP)
        try:
            result['before'] = app_info(dev, trace)
            if args.action == 'probe':
                app_command(dev, 0xA0, trace)
        finally:
            dev.close()
        if args.action == 'probe':
            dev = open_device(ISP, timeout=20)
            loader = Loader(dev, trace)
            try:
                result['isp'] = loader.inspect()
            finally:
                try:
                    loader.command(0xAB, reset=True)
                finally:
                    dev.close()
            dev = open_device(APP, timeout=20)
            try:
                result['after'] = app_info(dev, trace)
            finally:
                dev.close()
            if result['before'] != result['after']:
                raise IOError('сведения приложения изменились после ISP')
        result['complete'] = True
    finally:
        trace.result(result)
        trace.file.close()
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
