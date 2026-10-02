#!/usr/bin/env python3
"""Превращает захват Saleae Logic в текст.

Принимает то, что отдаёт экспорт Logic 2:

  * .bin  — Export Raw Data → Binary (один файл на канал), сырые переходы;
  * .csv  — Export Raw Data → CSV, сырые переходы (Time [s], Channel N);
  * .csv  — экспорт таблицы анализатора (колонка data/value с готовыми байтами).

Для сырых форматов сам режет поток на UART-кадры; --brute перебирает стандартные
скорости и полярность и показывает, какая даёт осмысленный текст.

Несколько таблиц сразу сливаются в одну хронологию по времени — так видно, что
на каком порту происходит раньше. Источник подписывается именем файла.

    tools/uart_text.py cap.bin --brute
    tools/uart_text.py cap.bin --baud 4800
    tools/uart_text.py table.csv
    tools/uart_text.py pin13-8051.txt pin14-tensilica.txt --gap 1
"""

import argparse
import bisect
import csv
import os
import struct
import sys

STD_BAUDS = [1200, 2400, 4800, 9600, 14400, 19200, 28800, 38400, 57600,
             76800, 115200, 128000, 230400, 250000, 460800, 921600]


def read_saleae_bin(path):
    """Официальный бинарный экспорт Logic 2 → (initial_state, [времена переходов])."""
    with open(path, 'rb') as f:
        blob = f.read()
    if blob[:8] != b'<SALEAE>':
        sys.exit(f'{path}: не бинарный экспорт Saleae (нет сигнатуры <SALEAE>)')
    version, ftype = struct.unpack_from('<ii', blob, 8)
    if ftype != 0:
        sys.exit(f'{path}: это не цифровой канал (type={ftype}); нужен цифровой экспорт')
    initial, _begin, _end, count = struct.unpack_from('<IddQ', blob, 16)
    times = struct.unpack_from(f'<{count}d', blob, 44)
    return initial, list(times)


def read_raw_csv(path, channel):
    """CSV сырых данных: строки на каждом переходе. → (initial_state, времена)."""
    with open(path, newline='') as f:
        rows = list(csv.reader(f))
    header = [h.strip() for h in rows[0]]
    tcol = 0
    if channel is None:
        cands = [i for i, h in enumerate(header) if i != tcol]
        if len(cands) != 1:
            sys.exit(f'в файле несколько каналов {header[1:]}; укажите --channel')
        vcol = cands[0]
    else:
        matches = [i for i, h in enumerate(header) if str(channel) in h]
        if not matches:
            sys.exit(f'канал {channel} не найден среди {header}')
        vcol = matches[0]

    times, initial, prev = [], None, None
    for row in rows[1:]:
        if len(row) <= vcol or not row[tcol].strip():
            continue
        t = float(row[tcol])
        v = int(float(row[vcol]))
        if initial is None:
            initial, prev = v, v
            continue
        if v != prev:
            times.append(t)
            prev = v
    return (initial or 0), times


ESCAPES = {'\\r': 13, '\\n': 10, '\\t': 9, '\\0': 0, '\\a': 7, '\\b': 8,
           '\\f': 12, '\\v': 11, '\\\\': 92, 'COMMA': 0x2C}


def parse_value(s):
    """Одна ячейка колонки Value/Data. Logic пишет её в выбранном радиксе:
    ASCII — сам символ либо экранированная последовательность (`\\r`, `\\xFF`,
    `COMMA` вместо запятой), Hexadecimal — `0x41`, Decimal — `65`."""
    if s in ESCAPES:
        return ESCAPES[s]
    if s.lower().startswith('\\x') or s.lower().startswith('0x'):
        return int(s[2:], 16)
    if len(s) == 1:
        return ord(s)
    if s.isdigit():
        return int(s)
    return None


def read_table_csv(path):
    """Экспорт таблицы анализатора → (байты, времена)."""
    with open(path, newline='') as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return b'', []
    keys = {k.lower().strip(): k for k in rows[0] if k}
    col = next((keys[k] for k in ('value', 'data', 'mosi', 'miso') if k in keys), None)
    if col is None:
        return None, None
    tcol = next((keys[k] for k in keys if k.startswith('time') or k == 'start_time'), None)
    out, times = bytearray(), []
    for r in rows:
        raw = r[col] or ''
        if not raw:
            continue
        s = raw.strip() or raw          # пустой после strip — значит сам байт пробельный
        # кадр с ошибкой формата — это не байт, а мусор на линии
        if any('error' in k.lower() and (r[k] or '').strip() for k in r if k):
            continue
        b = parse_value(s)
        if b is None:
            continue
        out.append(b)
        times.append(float(r[tcol]) if tcol and r.get(tcol) else None)
    return bytes(out), times


def level_at(initial, times, t):
    """Уровень линии в момент t: чётное число переходов до t — исходный уровень."""
    return initial ^ (bisect.bisect_right(times, t) & 1)


def decode_uart(initial, times, baud, bits=8, stop=1.0, parity=None, invert=False):
    """Разбор потока переходов в байты. Возвращает (байты, число ошибок стоп-бита)."""
    if not times:
        return b'', 0
    bit = 1.0 / baud
    idle, out, errors = 1, bytearray(), 0
    t = times[0]
    end = times[-1] + bit
    while t < end:
        cur = level_at(initial, times, t) ^ (1 if invert else 0)
        if cur == idle:                                   # ждём фронт старт-бита
            i = bisect.bisect_right(times, t)
            if i >= len(times):
                break
            t = times[i]
            continue
        start = t
        if level_at(initial, times, start + bit / 2) ^ (1 if invert else 0) != 0:
            t = start + bit / 2                           # глитч, не старт-бит
            continue
        val = 0
        for i in range(bits):                             # LSB первым
            s = start + bit * (1.5 + i)
            val |= (level_at(initial, times, s) ^ (1 if invert else 0)) << i
        pos = start + bit * (1.5 + bits)
        if parity:
            pos += bit
        if level_at(initial, times, pos) ^ (1 if invert else 0) != 1:
            errors += 1
        out.append(val)
        t = start + bit * (1 + bits + (1 if parity else 0) + stop)
    return bytes(out), errors


def score(data):
    """Доля печатных ASCII — по ней и выбирается верная скорость."""
    if not data:
        return 0.0
    good = sum(1 for b in data if 32 <= b < 127 or b in (9, 10, 13))
    return good / len(data)


def to_text(data, times=None, gap=0.0):
    """Байты → текст. Если известны времена и задан gap, паузы длиннее gap
    отмечаются меткой — иначе в логе не видно, где кончился один этап загрузки."""
    out = []
    for i, b in enumerate(data):
        if times and gap and i and times[i] and times[i - 1] \
                and times[i] - times[i - 1] > gap:
            out.append(f'\n[пауза {times[i] - times[i - 1]:.2f} с, t={times[i]:.3f}]\n')
        out.append(chr(b) if (32 <= b < 127 or b in (10, 13, 9)) else f'\\x{b:02x}')
    return ''.join(out)


def split_lines(data, times):
    """Байты со временами → [(время первого байта строки, текст строки)]."""
    lines, cur, start = [], [], None
    for b, t in zip(data, times):
        if b == 13:                      # \r игнорируем, строку заканчивает \n
            continue
        if start is None:
            start = t
        if b == 10:
            lines.append((start, ''.join(cur)))
            cur, start = [], None
            continue
        cur.append(chr(b) if (32 <= b < 127 or b == 9) else f'\\x{b:02x}')
    if cur:
        lines.append((start, ''.join(cur)))
    return lines


def merge(paths, gap):
    """Несколько таблиц анализатора → одна хронология с пометкой источника.
    Имя источника берётся из имени файла, поэтому называйте их по контакту."""
    rows = []
    for p in paths:
        data, times = read_table_csv(p)
        if data is None:
            sys.exit(f'{p}: это не таблица анализатора; слияние работает только с ними')
        if any(t is None for t in times):
            sys.exit(f'{p}: в таблице нет колонки времени, сопоставить не с чем')
        name = os.path.basename(p).rsplit('.', 1)[0]
        rows += [(t, name, s) for t, s in split_lines(data, times)]
    rows.sort(key=lambda r: r[0])
    width = max((len(r[1]) for r in rows), default=0)
    prev = None
    for t, name, s in rows:
        if prev is not None and gap and t - prev > gap:
            print(f'\n[пауза {t - prev:.2f} с]\n')
        print(f'{t:12.6f}  {name:<{width}}  {s}')
        prev = t


def hexdump(data):
    for off in range(0, len(data), 16):
        chunk = data[off:off + 16]
        hexs = ' '.join(f'{b:02x}' for b in chunk)
        text = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
        print(f'{off:08x}  {hexs:<47}  |{text}|')


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('path', nargs='+',
                    help='один файл — расшифровка; несколько таблиц — общая хронология')
    ap.add_argument('--baud', type=int, default=4800)
    ap.add_argument('--channel', type=int, default=None, help='номер канала в CSV')
    ap.add_argument('--bits', type=int, default=8)
    ap.add_argument('--stop', type=float, default=1.0)
    ap.add_argument('--parity', action='store_true', help='есть бит чётности')
    ap.add_argument('--invert', action='store_true', help='инвертированная линия')
    ap.add_argument('--brute', action='store_true', help='перебрать скорости и полярность')
    ap.add_argument('--hex', action='store_true', help='вывести дампом, а не текстом')
    ap.add_argument('--gap', type=float, default=0.5,
                    help='отмечать в тексте паузы длиннее N секунд (0 — не отмечать)')
    args = ap.parse_args()

    if len(args.path) > 1:
        merge(args.path, args.gap)
        return
    path = args.path[0]

    with open(path, 'rb') as f:
        is_bin = f.read(8) == b'<SALEAE>'

    if is_bin:
        initial, times = read_saleae_bin(path)
    else:
        table, tstamps = read_table_csv(path)
        if table is not None:
            print(f'# таблица анализатора: {len(table)} байт', file=sys.stderr)
            if args.hex:
                hexdump(table)
            else:
                print(to_text(table, tstamps, args.gap))
            return
        initial, times = read_raw_csv(path, args.channel)

    print(f'# переходов: {len(times)}, исходный уровень: {initial}', file=sys.stderr)
    measured = None
    if times:
        gaps = sorted(times[i + 1] - times[i] for i in range(len(times) - 1))
        if gaps:
            # Оценка берётся не по минимуму, а по первому проценту: одиночный
            # узкий выброс в захвате иначе уводит её на порядки.
            typical = gaps[len(gaps) // 100]
            measured = 1 / typical
            print(f'# кратчайший интервал между фронтами: {gaps[0] * 1e6:.2f} мкс; '
                  f'типичный {typical * 1e6:.2f} мкс → оценка скорости '
                  f'{measured:,.0f} бод', file=sys.stderr)

    if args.brute:
        results = []
        # Измеренную скорость обязательно в перебор: она не обязана попадать в
        # стандартный ряд. У этого железа 8051 печатает на 4823 бод, и разбор на
        # ближайших «правильных» 4800 бод даёт накопительный дрейф — на участках,
        # где байты идут вплотную, он съедает целый бит и молча портит строки
        # (см. docs/uart-console.md).
        cands = list(STD_BAUDS)
        if measured and 300 < measured < 2e6:
            cands.append(int(round(measured)))
        for baud in cands:
            for inv in (False, True):
                data, errs = decode_uart(initial, times, baud, args.bits, args.stop,
                                         args.parity, inv)
                results.append((score(data), -errs, baud, inv, data))
        results.sort(reverse=True)
        print('# доля печатных  ошибок  скорость  инверсия  байт', file=sys.stderr)
        for s, negerr, baud, inv, data in results[:8]:
            print(f'#   {s:6.2%}      {-negerr:5d}   {baud:7d}  {str(inv):>8}  {len(data)}',
                  file=sys.stderr)
        _, _, baud, inv, data = results[0]
        print(f'# лучший вариант: {baud} бод, инверсия={inv}', file=sys.stderr)
    else:
        data, errs = decode_uart(initial, times, args.baud, args.bits, args.stop,
                                 args.parity, args.invert)
        print(f'# {len(data)} байт, ошибок стоп-бита: {errs}, '
              f'печатных {score(data):.1%}', file=sys.stderr)
        if data and errs > len(data) * 0.01:
            hint = f', попробуйте --baud {int(round(measured))}' if measured else ''
            print(f'# ВНИМАНИЕ: ошибок стоп-бита {errs / len(data):.0%} — скорость '
                  f'скорее всего не та{hint}. Строки при этом не пропадают, а тихо '
                  f'превращаются в мусор', file=sys.stderr)

    hexdump(data) if args.hex else print(to_text(data))


if __name__ == '__main__':
    main()
