#!/usr/bin/env python3
"""Чтение U4002 командой 0x4A через собственную прошивку U7005.

Сначала проверяет E2/U7EX; штатному MSI никогда не посылает Report 4/0x4A.
--enter использует существующую подготовку ISP из isp_read.py. Для возврата
скалера после полного ISP нужно передёрнуть питание. --reuse продолжает
уже подготовленный сеанс. Ничего не стирает и не программирует.
"""
import argparse
import hashlib
import json
import struct
import time
from pathlib import Path

STATUS = {1:'неверный запрос', 2:'мост не в режиме I2C', 3:'ошибка I2C/таймаут',
          4:'неверный заголовок или XOR скалера', 5:'страница не загружена', 6:'неверный token'}


class UnsupportedExtensionError(IOError):
    """Discovery answered, but its protocol cannot be used by this client."""


class FlashReader:
    def __init__(self, device):
        self.device = device
        self.token = 0
        self.discovered = False

    def exchange(self, request, match):
        request = request.ljust(64, b'\0')
        if self.device.write(request) != 64:
            raise IOError('неполная запись HID')
        deadline = time.monotonic()+3
        while time.monotonic() < deadline:
            reply = bytes(self.device.read(64, timeout_ms=250))
            if len(reply) == 64 and match(reply):
                return reply
        raise TimeoutError('нет ответа U7005 (для E2 требуется собственная прошивка)')

    def discover(self):
        self.discovered = False
        reply = self.exchange(b'\x01\xe2', lambda r:r[:6] == b'\x01\x5aU7EX')
        if reply[6:12] != b'\x01\x4a\x01\x00\x02\x34':
            raise UnsupportedExtensionError('неподдерживаемая версия расширения U7EX')
        self.discovered = True
        return {'protocol':1, 'command':'0x4A', 'page_bytes':512, 'chunk_bytes':52}

    def page(self, address):
        if not self.discovered:
            raise RuntimeError('сначала нужен успешный E2/U7EX discovery')
        if address % 512 or not 0 <= address <= 0x1fffe00:
            raise ValueError('страница вне U4002 или адрес не кратен 512')
        self.token = (self.token+1) & 65535
        data = bytearray()
        for offset in range(0,512,52):
            request = struct.pack('<BBBBHHI',4,0x4a,1,2 if offset else 1,self.token,offset,address)
            reply = self.exchange(request, lambda r:r[:3] == b'\x04\x4a\x01'
                                  and r[4:8] == request[4:8])
            if reply[3]:
                raise IOError(STATUS.get(reply[3],f'неизвестный статус {reply[3]}'))
            n = min(52,512-offset)
            if reply[8:12] != bytes([n, int(offset+n<512), 0, 2]):
                raise IOError('неверная длина или продолжение страницы')
            data.extend(reply[12:12+n])
        return bytes(data)

    def read(self, address, length):
        if not 0 <= address < 0x2000000 or not 0 < length <= 0x2000000-address:
            raise ValueError('диапазон должен лежать внутри 32 МиБ U4002')
        end = address+length
        for page_address in range(address & ~511, end, 512):
            page = self.page(page_address)
            yield page[max(0,address-page_address):min(512,end-page_address)]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--info', action='store_true', help='только проверить наличие расширения')
    ap.add_argument('--read', nargs=2, type=lambda s:int(s,0), metavar=('ADDRESS','LENGTH'))
    ap.add_argument('-o','--output',type=Path)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument('--enter',action='store_true',help='ввести работающий скалер в полный ISP')
    mode.add_argument('--reuse',action='store_true',help='скалер уже в полном ISP')
    mode.add_argument('--bootloader',action='store_true',help='скалер подготовлен bootloader-libre')
    args = ap.parse_args()
    if args.info and args.read:
        ap.error('--info и --read взаимоисключающие')
    if args.read and (not args.output or not (args.enter or args.reuse or args.bootloader)):
        ap.error('--read требует -o и одного из --enter/--reuse/--bootloader')
    if args.read:
        address,length = args.read
        if not length or not 0 <= address < 0x2000000 or not 0 < length <= 0x2000000-address:
            ap.error('диапазон должен лежать внутри 32 МиБ U4002')
        if args.output.exists() or args.output.with_suffix(args.output.suffix+'.json').exists():
            ap.error('выходной файл уже существует')
        if not args.output.parent.is_dir():
            ap.error('каталог результата не существует')
    from isp_read import Bridge
    bridge = Bridge()
    try:
        reader = FlashReader(bridge.dev)
        info = reader.discover()
        print(json.dumps(info, ensure_ascii=False))
        if not args.read:
            return
        if args.enter:
            bridge.enter()
        elif args.bootloader:
            bridge.enter_bootloader()
        else:
            bridge.enter_bridge_only()
        started = time.monotonic()
        digest = hashlib.sha256()
        with args.output.open('xb') as output:
            for block in reader.read(address,length):
                output.write(block)
                digest.update(block)
        info.update(address=address,length=length,sha256=digest.hexdigest(),seconds=time.monotonic()-started)
        with args.output.with_suffix(args.output.suffix+'.json').open('x') as meta:
            json.dump(info,meta,indent=2)
        print(f"Прочитано {length} байт за {info['seconds']:.2f} с: {args.output}")
    finally:
        bridge.dev.close()


if __name__ == '__main__':
    main()
