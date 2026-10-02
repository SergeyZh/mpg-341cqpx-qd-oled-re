#!/usr/bin/env python3
"""Разбирает захват USBPcap (.pcapng) и декодирует HID-обмен с монитором.

Wireshark под Windows пишет USB-захват как pcapng с типом канала
LINKTYPE_USBPCAP (249). Здесь минимальный разбор этого формата — без tshark,
которого под macOS обычно нет.

Два режима:

  --devices   таблица устройств: VID:PID, класс, строки, объём трафика.
              Этим проверяется, какие устройства монитора вообще перечислились;
              главный интерес — есть ли `0603:1234` (`docs/usb-isp.md`).

  (по умолчанию) декод обмена с мостом `1462:3fa4` (U7005). Первый байт HID-отчёта
              — номер команды диспетчера (`docs/mcu-u7005.md`); команда 0x01 несёт
              ASCII-кадр, завершённый `\\r`. Кадры печатаются парами запрос/ответ.

    tools/usbpcap_hid.py cap.pcapng --devices
    tools/usbpcap_hid.py cap.pcapng
    tools/usbpcap_hid.py cap.pcapng --table
    tools/usbpcap_hid.py cap.pcapng --vid 0603 --pid 1234

Формат кадра команды 0x01 разобран в `docs/usb-hid-msi.md`.
"""

import argparse
import collections
import struct
import sys

LINKTYPE_USBPCAP = 249

XFER = {0: 'ISOC', 1: 'INTR', 2: 'CTRL', 3: 'BULK'}

Packet = collections.namedtuple(
    'Packet', 'ts bus dev ep xfer dlen stage out payload')


def _blocks(blob):
    """pcapng → (тип блока, тело без заголовка и хвоста, порядок байт)."""
    off, endian = 0, '<'
    while off + 12 <= len(blob):
        btype, = struct.unpack_from(endian + 'I', blob, off)
        if btype == 0x0A0D0D0A:                       # Section Header Block
            magic, = struct.unpack_from('<I', blob, off + 8)
            endian = '<' if magic == 0x1A2B3C4D else '>'
        blen, = struct.unpack_from(endian + 'I', blob, off + 4)
        if blen < 12 or off + blen > len(blob):
            break
        yield btype, blob[off + 8:off + blen - 4], endian
        off += blen


def _tsresol(body, endian):
    """Разрешение отметок времени из опций IDB; по умолчанию микросекунды."""
    off = 8                                            # linktype, reserved, snaplen
    while off + 4 <= len(body):
        code, olen = struct.unpack_from(endian + 'HH', body, off)
        if code == 0:
            break
        if code == 9 and olen >= 1:                    # if_tsresol
            return body[off + 4]
        off += 4 + ((olen + 3) & ~3)
    return 6


def packets(path):
    """Пакеты USBPcap из файла. Заголовок USBPCAP_BUFFER_PACKET_HEADER —
    27 байт, у управляющих передач добавлен байт стадии."""
    with open(path, 'rb') as f:
        blob = f.read()
    scale, checked = 1e-6, False
    for btype, body, endian in _blocks(blob):
        if btype == 1:                                 # Interface Description Block
            linktype, = struct.unpack_from(endian + 'H', body, 0)
            if linktype != LINKTYPE_USBPCAP and not checked:
                sys.exit(f'{path}: тип канала {linktype}, а нужен USBPcap '
                         f'({LINKTYPE_USBPCAP}) — захват сделан не USBPcap')
            checked = True
            res = _tsresol(body, endian)
            scale = 2.0 ** -(res & 0x7F) if res & 0x80 else 10.0 ** -(res & 0x7F)
        elif btype == 6:                               # Enhanced Packet Block
            _, tsh, tsl, caplen, _ = struct.unpack_from(endian + 'IIIII', body, 0)
            raw = body[20:20 + caplen]
            if len(raw) < 27:
                continue
            hlen, = struct.unpack_from('<H', raw, 0)
            (_irp, _status, _func, info, bus, dev,
             ep, xfer, dlen) = struct.unpack_from('<QIHBHHBBI', raw, 2)
            stage = raw[27] if xfer == 2 and hlen >= 28 else None
            yield Packet(((tsh << 32) | tsl) * scale, bus, dev, ep, xfer, dlen,
                         stage, not (info & 1), raw[hlen:])


def collect(paths):
    """Дескрипторы, строки и объём трафика по каждому адресу устройства."""
    descs, strings, traffic, eps = {}, {}, collections.Counter(), {}
    for path in paths:
        for p in packets(path):
            key = (p.bus, p.dev)
            traffic[key] += len(p.payload)
            eps.setdefault(key, set()).add((XFER.get(p.xfer, f'x{p.xfer:02x}'), p.ep))
            d = p.payload
            if len(d) >= 18 and d[0] == 0x12 and d[1] == 0x01:
                vid, pid = struct.unpack_from('<HH', d, 8)
                descs[key] = (vid, pid, d[4], d[5], d[6])
            elif len(d) >= 4 and d[1] == 0x03 and 4 <= d[0] <= len(d):
                try:
                    s = d[2:d[0]].decode('utf-16-le')
                except UnicodeDecodeError:
                    continue
                if s.isprintable() and len(s) > 2:
                    strings.setdefault(key, set()).add(s)
    return descs, strings, traffic, eps


def cmd_devices(paths):
    descs, strings, traffic, eps = collect(paths)
    print(f'{"шина/адрес":<12} {"VID:PID":<10} {"класс":<14} {"байт":>9}  '
          f'точки / строки')
    for key in sorted(traffic, key=lambda k: -traffic[k]):
        vid, pid, cls, sub, proto = descs.get(key, (0, 0, 0, 0, 0))
        ident = f'{vid:04x}:{pid:04x}' if key in descs else '—'
        klass = f'{cls:02x}/{sub:02x}/{proto:02x}' if key in descs else ''
        tail = ' '.join(f'{x}/ep{e:02x}' for x, e in sorted(eps[key]))
        names = ', '.join(sorted(strings.get(key, ())))
        print(f'{key[0]}/{key[1]:<10} {ident:<10} {klass:<14} {traffic[key]:>9}  '
              f'{tail}{"  « " + names if names else ""}')


def show(data):
    """Печатные символы как есть, остальное — <hh>."""
    return ''.join(chr(c) if 32 <= c < 127 else f'<{c:02x}>' for c in data)


def report_body(payload):
    """Тело HID-отчёта: команда и полезная часть без хвостовых нулей."""
    if not payload:
        return None, b''
    body = payload[1:]
    if payload[0] == 0x01 and b'\r' in body:
        body = body[:body.index(b'\r') + 1]
    else:
        body = body.rstrip(b'\x00')
    return payload[0], body


def cmd_frames(paths, vid, pid, table):
    descs, _, _, _ = collect(paths)
    targets = {key for key, d in descs.items() if (d[0], d[1]) == (vid, pid)}
    if not targets:
        sys.exit(f'{vid:04x}:{pid:04x} в захвате не перечислялось — '
                 f'посмотрите tools/usbpcap_hid.py --devices')
    pairs, rows = collections.Counter(), []
    for path in paths:
        t0, pending = None, None
        for p in packets(path):
            if (p.bus, p.dev) not in targets or p.xfer != 1 or not p.payload:
                continue
            t0 = p.ts if t0 is None else t0
            out = not p.ep & 0x80
            cmd, body = report_body(p.payload)
            rows.append((p.ts - t0, out, cmd, body))
            if out:
                pending = (cmd, body)
            elif pending is not None:
                pairs[(pending[0], show(pending[1]), cmd, show(body))] += 1
                pending = None
    if table:
        print(f'{"cmd":>4}  {"запрос":<20} -> {"ответ":<34} повторов')
        for (qc, q, ac, a), n in sorted(pairs.items(), key=lambda kv: kv[0][1]):
            print(f'  0x{qc:02x}  {q:<20} -> 0x{ac:02x} {a:<30} {n}')
        return
    for ts, out, cmd, body in rows:
        print(f'{ts:8.3f}  {"→" if out else "←"}  0x{cmd:02x}  {show(body)}')


def cmd_isp(paths, vid, pid, save):
    """Отчёт 0x04 — мост в I²C. Собирает образ прошивки и сводит команды.

    Формат: 04 | подкоманда | адрес чтения I²C | 00 | адрес записи I²C | посылка.
    Образ идёт слейву 0xB0 блоками по 4 КиБ: bd задаёт адрес, дальше
    bf (58 байт) + 67×c0 (по 60) + c1 (18). Управление идёт слейву 0x6E
    пакетами `[длина][опкод][аргументы]`, опкоды 0x78 (запись регистра) и
    0x87 (чтение) — `docs/usb-isp-protocol.md`.
    """
    descs, _, _, _ = collect(paths)
    targets = {key for key, d in descs.items() if (d[0], d[1]) == (vid, pid)}
    blocks, transfers, addr, cur = {}, [], None, bytearray()
    regs_w, regs_r, cmds = collections.Counter(), collections.Counter(), collections.Counter()
    for path in paths:
        for p in packets(path):
            if (p.bus, p.dev) not in targets or p.xfer != 1 or not p.payload:
                continue
            d = p.payload
            if d[0] != 4 or p.ep & 0x80:
                continue
            sub = d[1]
            # у продолжающих пакетов c0 пятый байт — данные, а не адрес слейва,
            # поэтому поток образа опознаётся по подкоманде, а не по d[4]
            if sub == 0xBD:
                addr = int.from_bytes(d[5:9], 'big')
            elif sub == 0xBF:
                cur = bytearray(d[6:64])
            elif sub == 0xC0:
                cur += d[4:64]
            elif sub == 0xC1:
                cur += d[4:22]
                if addr is not None:
                    transfers.append((addr, bytes(cur)))
                    blocks[addr] = bytes(cur)
                cur = bytearray()
            elif d[4] == 0x6E and len(d) > 8:
                length, op = d[5], d[6]
                if op == 0x78 and length >= 4:
                    regs_w[((d[7] << 8) | d[8], d[9])] += 1
                elif op == 0x87 and length >= 3:
                    regs_r[(d[7] << 8) | d[8]] += 1
                else:
                    cmds[(length, op)] += 1
    print(f'передач блоков: {len(transfers)}, уникальных адресов: {len(blocks)}')
    repeated = collections.Counter(address for address, _ in transfers)
    repeated = {address: count for address, count in repeated.items() if count > 1}
    if repeated:
        print('повторённые адреса: ' + ' '.join(
            f'{address:#x}×{count}' for address, count in sorted(repeated.items())))
    if blocks:
        lo, hi = min(blocks), max(blocks)
        print(f'адреса: {lo:#x}..{hi:#x}, всего {len(blocks) * 0x1000} байт')
        img = bytearray(b'\xff' * (hi + 0x1000))
        for a, v in blocks.items():
            img[a:a + 0x1000] = v
        if save:
            with open(save, 'wb') as f:
                f.write(bytes(img))
            print(f'образ записан: {save}')
    print(f'\nзапись регистров (0x78), {sum(regs_w.values())} шт:')
    for (reg, val), n in sorted(regs_w.items()):
        print(f'   {reg:#06x} = {val:#04x}   ×{n}')
    print(f'\nчтение регистров (0x87), {sum(regs_r.values())} шт:')
    print('   ' + ' '.join(f'{r:#06x}' for r in sorted(regs_r)))
    print(f'\nпрочие команды на 0x6E:')
    for (length, op), n in cmds.most_common():
        print(f'   длина {length:2d} опкод {op:#04x}   ×{n}')


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('files', nargs='+', help='захваты .pcapng от USBPcap')
    ap.add_argument('--devices', action='store_true',
                    help='таблица устройств вместо декода кадров')
    ap.add_argument('--table', action='store_true',
                    help='свести кадры в уникальные пары запрос/ответ')
    ap.add_argument('--isp', action='store_true',
                    help='разобрать обновление: собрать образ и свести команды I²C')
    ap.add_argument('--save', metavar='ФАЙЛ',
                    help='с --isp: куда записать собранный образ')
    ap.add_argument('--vid', default='1462', help='VID моста (по умолчанию 1462)')
    ap.add_argument('--pid', default='3fa4', help='PID моста (по умолчанию 3fa4)')
    args = ap.parse_args()
    if args.devices:
        cmd_devices(args.files)
    elif args.isp:
        cmd_isp(args.files, int(args.vid, 16), int(args.pid, 16), args.save)
    else:
        cmd_frames(args.files, int(args.vid, 16), int(args.pid, 16), args.table)


if __name__ == '__main__':
    main()
