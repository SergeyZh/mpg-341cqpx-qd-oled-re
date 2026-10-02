#!/usr/bin/env python3
r"""Запись произвольных данных в SPI-флеш монитора штатным ISP-автоматом.

Утилита пишет ровно те байты, которые ей дали, и ничего больше. По умолчанию она
считает скалер уже введённым в ISP и только поднимает U7005 в режим сырого I²C.
`--enter` выполняет перед записью полный штатный вход, а `--bootloader` продолжает
вход, подготовленный recovery-загрузчиком, без команды `580040:`. `--recover` после
записи использует проверенный F1D-дескриптор FW.034 либо watchdog reset из
распознанного пустого состояния libre recovery (GD25Q256E, EAR=0).
Код выхода 2 после recovery означает, что сброс отправлен, но USB/UART-проверка
недоступна (в том числе при возврате в Power Off), а не доказанную неудачу загрузки.

АДРЕС

`--address` — сквозной адрес во флеше, 25 бит. Бит 24 — номер физического банка
GD25Q256, младшие 24 бита — смещение внутри банка:

    0x0007000    банк 0, смещение 0x007000   (нижние 16 МиБ)
    0x1300000    банк 1, смещение 0x300000   (верхние 16 МиБ)

Банк уходит ISP-автомату подкомандой `a2 0f` и той же величиной ставится EAR
микросхемы; исходный EAR восстанавливается на выходе. Одна запись не может
пересекать границу банков — нужны два вызова.

ДВА РЕЖИМА

program (по умолчанию) — запись без стирания. Годится, когда цель стёрта (везде
`FF`) или когда надо только погасить биты `1 → 0`. Адрес и длина любые:
утилита сама режет запись на выровненные куски по 512 байт и дополняет края
`FF`, а программирование `FF` байт не меняет — соседние данные не страдают.
Если цель не стёрта, получится «старое AND новое»; утилита это ловит и по
умолчанию отказывается писать в нестёртую область.

--erase — запись со стиранием. Штатный 4-КиБ цикл стирает сектор целиком,
поэтому адрес и длина обязаны быть кратны 0x1000: иначе пришлось бы затереть
чужие данные. Нужен всегда, когда в целевой области уже что-то лежит и биты
должны идти `0 → 1`.

Первые два сектора каждого банка (`0x0000…0x1FFF`) защищены отдельно. Любое их
пересечение отклоняется до открытия USB; осознанная запись первичного загрузчика
требует явного `--allow-bootloader`.

ПРОВЕРКА

Записанное сверяется контрольными суммами (подкоманда `0x36`, сумма 512 байт),
без чтения данных: сумма снимается до записи, из неё выводится ожидаемая после,
и она сверяется с фактической. Единственное исключение — `--force-dirty`: там
прежнее содержимое неизвестно и сумму предсказать нельзя, поэтому записанные
байты (и только они) перечитываются.

Для read-back и --force-dirty по умолчанию используется 0x4A, если мост ответил
на E2/U7EX. Иначе сохраняется старый SPI-путь. --flash-read-method legacy отключает
обнаружение, --flash-read-method 4a требует расширение. Ошибка чтения страницы
не маскируется повтором через другой транспорт.

ПРИМЕРЫ

Токен подтверждения считать вручную не надо: запустите без `--confirm`, и
утилита напечатает нужный. С `--dry-run` подтверждение не требуется вовсе.

1. Посмотреть кадры и ничего не послать:

    .venv/bin/python tools/isp_write.py --address 0x1300000 \
        --input out/stbc.bin --dry-run

2. Полный сеанс одним HID handle, включая вход и recovery:

    .venv/bin/python tools/isp_write.py --enter --address 0x1300000 \
        --input out/stbc.bin --confirm WRITE-1-300000-F026 --recover

3. Образ 0xF026 байт в заведомо стёртую область — стирание не нужно, пишется
   ровно 0xF026 байт, хвост сектора остаётся `FF`:

    .venv/bin/python tools/isp_write.py --address 0x1300000 \
        --input out/stbc.bin --confirm WRITE-1-300000-F026

4. То же место, но там уже что-то лежит. Стирается сектор целиком, значит и
   отдать надо целые секторы — дополняем образ до 0x10000:

    .venv/bin/python -c "d=open('out/stbc.bin','rb').read(); \
        open('out/sector.bin','wb').write(d.ljust(0x10000, b'\xff'))"
    .venv/bin/python tools/isp_write.py --address 0x1300000 \
        --input out/sector.bin --erase --confirm WRITE-1-300000-10000

5. Один байт по произвольному адресу — погасить маркер слота `0x007FFF`
   (`AA → 00`). Биты идут только вниз, поэтому стирание не нужно:

    printf '\x00' > out/zero.bin
    .venv/bin/python tools/isp_write.py --address 0x7FFF --input out/zero.bin \
        --force-dirty --confirm WRITE-0-007FFF-1

   Записан будет ровно один байт: остальные 511 байт единицы уйдут как `FF` и
   ничего не изменят. Сверка здесь идёт чтением этого байта.

6. Обратно `00 → AA` так уже не записать — нужно стирание, а стирается весь
   сектор `0x7000`. Значит, его содержимое надо иметь целиком: взять из дампа
   `flash/u4002_a.bin`, из захвата обновления или вычитать с монитора
   (`isp_read.py --read`, ~30 с на 4 КиБ, читает банк по текущему EAR),
   поправить нужные байты и залить сектор целиком:

    .venv/bin/python -c "d=bytearray(open('out/slot.bin','rb').read()); \
        d[0xFFF]=0xAA; open('out/slot.bin','wb').write(d)"
    .venv/bin/python tools/isp_write.py --address 0x7000 --input out/slot.bin \
        --erase --confirm WRITE-0-007000-1000

7. Диапазон через границу банков не принимается — разбить на два вызова:

    .venv/bin/python tools/isp_write.py --address 0xFFF000 \
        --input out/lower.bin --erase --confirm WRITE-0-FFF000-1000
    .venv/bin/python tools/isp_write.py --address 0x1000000 \
        --input out/upper.bin --erase --confirm WRITE-1-000000-1000

Разбор самого протокола — `docs/usb-isp-protocol.md`, § «Служебные команды».
Без `--enter` или `--bootloader` предполагается, что скалер уже в ISP-режиме.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time

from isp_block_transfer import BLOCK_SIZE, transfer_block
from isp_read import (
    A700, F0C0, OP_SPI_RUN, RD, WR, Bridge, RecoveryVerificationUnavailable,
    add_flash_read_argument, auto_int, recover_stbc, report04, xor,
)


UNIT = 0x200                    # шаг адресации подкоманд 0x3C и 0x36
BANK_SIZE = 0x1000000           # 16 МиБ на банк, бит 24 адреса — номер банка
FLASH_SIZE = 2 * BANK_SIZE
ERASED_UNIT_SUM = (0xFF * UNIT) & 0xFFFF
KEY = bytes.fromhex("f0 0f 6e 91 13 ec")
JEDEC_GD25Q256 = bytes.fromhex("c8 40 19")
SLOT_AREA = range(0x006000, 0x008000)
# bootloader-libre currently occupies the first two 4-KiB sectors.
BOOTLOADER_AREA = range(0x000000, 0x002000)

# Только опросы состояния микросхемы и переключение EAR. Опкодов, меняющих
# содержимое флеша, здесь нет и быть не должно: вся запись идёт через
# ISP-автомат, а не через окно 0xA700.
SPI_OPCODES = {0x9F: "RDID", 0x05: "RDSR-1", 0x35: "RDSR-2", 0x0B: "Fast Read",
               0xC8: "RDEAR", 0x06: "WREN", 0xC5: "WREAR"}
READ_CHUNK = 249                # предел приёмного окна 0xA700


def _pad64(data: bytes) -> bytes:
    if len(data) > 64:
        raise ValueError(f"HID report длиннее 64: {len(data)}")
    return data + bytes(64 - len(data))


def spi_raw(br: Bridge, send: bytes, recv_len: int) -> bytes:
    """Одна SPI-команда через окно 0xA700; список опкодов ограничен."""
    if not send or send[0] not in SPI_OPCODES:
        raise ValueError(f"опкод {send[0]:#04x} не разрешён этой утилите")
    buf = A700 + 2
    recv = buf + len(send)
    for reg, value in (
        (F0C0 + 0, 0x13),
        (F0C0 + 1, A700 >> 8), (F0C0 + 2, A700 & 0xFF),
        (F0C0 + 3, buf >> 8), (F0C0 + 4, buf & 0xFF),
        (F0C0 + 5, recv >> 8), (F0C0 + 6, recv & 0xFF),
        (A700 + 0, len(send)), (A700 + 1, recv_len),
    ):
        br.write_reg(reg, value)
    for index, value in enumerate(send):
        br.write_reg(buf + index, value)
    br._xfer(report04(0xAF, RD, WR, [OP_SPI_RUN]), 0xAF)
    if not br.dry:
        time.sleep(0.25)          # без паузы движок отдаёт недостоверный ответ
    return bytes(br.read_reg(recv + index) for index in range(recv_len))


def read_flash(br: Bridge, offset: int, length: int) -> bytes:
    """Read-back from current EAR via discovered 4A or the legacy SPI path."""
    return br.read_flash(offset, length, chunk=READ_CHUNK)


def read_ear(br: Bridge) -> int:
    return 0 if br.dry else spi_raw(br, b"\xC8", 1)[0]


def set_ear(br: Bridge, bank: int) -> None:
    """Переключить volatile Extended Address Register микросхемы."""
    spi_raw(br, b"\x06", 0)
    if not br.dry and not spi_raw(br, b"\x05", 1)[0] & 0x02:
        raise RuntimeError("WREN не выставил WEL перед WREAR")
    spi_raw(br, bytes([0xC5, bank]), 0)
    if br.dry:
        return
    status = spi_raw(br, b"\x05", 1)[0]
    if status & 0x01:
        raise RuntimeError(f"WREAR ещё выполняется, status-1={status:02x}")
    got = read_ear(br)
    if got != bank:
        raise RuntimeError(f"RDEAR={got:02x}, ожидался {bank:02x}")
    print(f"EAR={bank:02x}", flush=True)


def select_bank(br: Bridge, bank: int) -> None:
    """`a2 0f <банк>` — выбор физического банка для ISP-автомата."""
    reply = br._xfer(report04(0xA2, RD, WR, [0x0F, bank]), 0xA2)
    if br.dry:
        return
    if reply[:8] != bytes([0x04, 0xA2, 0x01, 0x00, RD, 0x02, 0xF0, bank]):
        raise IOError(f"a2 0f {bank:02x}: неожиданный ответ {reply[:9].hex(' ')}")
    print(f"ISP-автомат переключён на банк {bank}", flush=True)


def unit_sum(br: Bridge, index: int) -> int:
    """`0x36` — 16-битная сумма 512 байт по адресу index * 0x100."""
    frame = b"\x36" + index.to_bytes(2, "big") + b"\x00"
    reply = br._xfer(report04(0xB5, RD, WR, frame), 0xB5)
    if br.dry:
        return ERASED_UNIT_SUM
    if reply[:7] != bytes.fromhex("04 b5 01 00 6f 03 c9"):
        raise IOError(f"0x36 {index:#06x}: неожиданный ответ {reply[:10].hex(' ')}")
    if reply[9] != xor(RD, reply[5:9]):
        raise IOError(f"0x36 {index:#06x}: неверный XOR {reply[:10].hex(' ')}")
    return int.from_bytes(reply[7:9], "big")


def stream_reports(index: int, data: bytes) -> tuple[bytes, ...]:
    """Девять отчётов подкоманды `0x3C`: запись 512 байт по index * 0x100.

    Все девять — одна I²C-посылка: адрес слейва, байт длины `0x00`, кадр из
    522 байт и XOR. Мост режет её на 60 + 7 x 60 + 45 байт (`write_len` в
    `docs/mcu-u7005.md`), поэтому границы отчётов ниже не круглые.
    """
    if len(data) != UNIT:
        raise ValueError(f"нужно ровно {UNIT} байт, получено {len(data)}")
    frame = b"\x3C" + index.to_bytes(2, "big") + b"\x00" + KEY + data
    payload = bytes([WR, 0x00]) + frame + bytes([xor(WR, b"\x00" + frame)])
    if len(payload) != 525:
        raise AssertionError(f"неверная длина посылки: {len(payload)}")
    reports = [_pad64(b"\x04\xB6\x00\x00" + payload[0:60])]
    reports += [
        _pad64(b"\x04\xB7\x00\x00" + payload[60 + 60 * part: 120 + 60 * part])
        for part in range(7)
    ]
    reports.append(_pad64(b"\x04\xB8\x6F\x00" + payload[480:525]))
    return tuple(reports)


def program_unit(br: Bridge, index: int, data: bytes) -> None:
    reports = stream_reports(index, data)
    for report in reports[:-1]:
        if br.dry:
            print("  → " + report.rstrip(bytes(1)).hex(" "))
        else:
            br.dev.write(report)
    reply = br._xfer(reports[-1], 0xB8)
    if br.dry:
        return
    if reply[:7] != bytes.fromhex("04 b8 01 00 6f 01 c3"):
        raise IOError(f"0x3C {index:#06x}: неожиданный ответ {reply[:8].hex(' ')}")


def preflight(br: Bridge) -> None:
    """Только чтения: связь, та ли микросхема, не включена ли защита блоков."""
    jedec = spi_raw(br, b"\x9F", 3)
    if br.dry:
        return
    if jedec != JEDEC_GD25Q256:
        raise RuntimeError(f"неожиданный JEDEC ID: {jedec.hex(' ')}")
    status1 = spi_raw(br, b"\x05", 1)[0]
    status2 = spi_raw(br, b"\x35", 1)[0]
    print(f"JEDEC={jedec.hex(' ')}, status-1={status1:02x}, status-2={status2:02x}",
          flush=True)
    if status1 & 0x3C:
        raise RuntimeError(
            f"выставлены биты защиты блоков BP0..BP3 (status-1={status1:02x}); "
            "утилита не снимает защиту сама — это запись в регистр микросхемы"
        )


def arm(br: Bridge, bank: int, sector_mode: bool) -> None:
    """Подготовка ISP-автомата — те же кадры, что в штатном прологе.

    Из захваченного пролога здесь нет двух вещей: потоков `0x3C` по индексу
    `0x007E`, которые гасят маркеры слотов (именно они переключили default boot
    2026-08-22), и пары `WREN`/`WRSR`, переписывающей status register
    микросхемы. Ни то, ни другое для записи не нужно.
    """
    br.write_reg(0xF067, 0x20)
    br._xfer(report04(0xAD, 0x00, WR, [0x99, 0x00]), 0xAD)
    br.write_reg(0xF134, br.read_reg(0xF134))
    br.write_reg(0xF11D, br.read_reg(0xF11D))
    br.write_reg(0xF11C, br.read_reg(0xF11C) | 0x40)
    select_bank(br, bank)
    if sector_mode:
        br._xfer(_pad64(b"\x04\xBC\x00\x00\xB0\xFF\xF2"), 0xBC)


def plan_units(offset: int, data: bytes) -> list[tuple[int, int, bytes]]:
    """Разбить запись на единицы (индекс, смещение внутри 512, данные)."""
    units = []
    position = 0
    while position < len(data):
        current = offset + position
        inside = current % UNIT
        count = min(UNIT - inside, len(data) - position)
        units.append((current // UNIT * 2, inside, data[position:position + count]))
        position += count
    return units


def write_program(br: Bridge, offset: int, data: bytes, force_dirty: bool) -> None:
    """Запись без стирания: только 1 → 0, соседние байты не затрагиваются."""
    units = plan_units(offset, data)
    print(f"program: {len(data):#x} байт, {len(units)} единиц по {UNIT}", flush=True)
    for number, (index, inside, chunk) in enumerate(units, 1):
        address = index * 0x100 + inside
        payload = (b"\xFF" * inside + chunk
                   + b"\xFF" * (UNIT - inside - len(chunk)))
        if force_dirty:
            # Прежнее содержимое неизвестно, сумму после записи не предсказать.
            # Поэтому здесь — единственное во всей утилите чтение данных, и
            # читаются ровно записанные байты, а не вся единица.
            program_unit(br, index, payload)
            got = read_flash(br, address, len(chunk))
            if not br.dry and got != chunk:
                first = next(i for i, (a, b) in enumerate(zip(got, chunk)) if a != b)
                raise RuntimeError(
                    f"адрес {address + first:#08x}: прочитано {got[first]:02x}, "
                    f"записывалось {chunk[first]:02x}. Биты без стирания идут "
                    "только 1 → 0, нужен --erase"
                )
        else:
            before = unit_sum(br, index)
            if len(chunk) == UNIT and before != ERASED_UNIT_SUM:
                raise RuntimeError(
                    f"единица {index:#06x} (адрес {index * 0x100:#08x}) не стёрта: "
                    f"сумма {before:04x}, у стёртой {ERASED_UNIT_SUM:04x}. Без "
                    "стирания биты идут только 1 → 0, нужен --erase или "
                    "--force-dirty. Если это первая единица прогона, возможен и "
                    "другой случай: ISP-автомат не принял выбор банка и 0x36 "
                    "отвечает мусором — тогда запись нельзя начинать вовсе"
                )
            expected = (before - 0xFF * len(chunk) + sum(chunk)) & 0xFFFF
            program_unit(br, index, payload)
            after = unit_sum(br, index)
            if not br.dry and after != expected:
                raise RuntimeError(
                    f"единица {index:#06x} (адрес {index * 0x100:#08x}): сумма "
                    f"после записи {after:04x}, ожидалась {expected:04x}. "
                    "Вероятнее всего область не была стёрта и получилось "
                    "«старое AND новое»"
                )
        if number % 8 == 0 or number == len(units):
            how = "чтением записанных байт" if force_dirty else "суммами"
            print(f"  {number}/{len(units)} проверено {how}", flush=True)


def write_sectors(br: Bridge, offset: int, data: bytes) -> None:
    """Запись со стиранием: только целые 4-КиБ секторы, только заданные."""
    count = len(data) // BLOCK_SIZE
    print(f"sector: {len(data):#x} байт, {count} секторов по {BLOCK_SIZE:#x} "
          "(каждый стирается целиком)", flush=True)
    for number in range(count):
        position = number * BLOCK_SIZE
        block = data[position:position + BLOCK_SIZE]
        words = transfer_block(br, offset + position, block)
        expected = tuple(sum(block[i:i + UNIT]) & 0xFFFF
                         for i in range(0, BLOCK_SIZE, UNIT))
        if not br.dry and words != expected:
            raise RuntimeError(
                f"сектор {offset + position:#08x}: суммы {[f'{w:04x}' for w in words]}, "
                f"ожидались {[f'{w:04x}' for w in expected]}"
            )
        print(f"  сектор {offset + position:#08x} записан и проверен суммами",
              flush=True)


def token(bank: int, offset: int, length: int) -> str:
    return f"WRITE-{bank}-{offset:06X}-{length:X}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--address", type=auto_int, required=True,
                        help="сквозной адрес во флеше; бит 24 — номер банка")
    parser.add_argument("--input", type=Path, required=True,
                        help="файл с данными; пишется целиком")
    parser.add_argument("--erase", action="store_true",
                        help="режим 4-КиБ секторов со стиранием вместо записи 1 → 0")
    parser.add_argument("--force-dirty", action="store_true",
                        help="разрешить program поверх нестёртой области; "
                             "проверка тогда идёт чтением записанных байт")
    parser.add_argument("--dry-run", action="store_true",
                        help="показать кадры, ничего не слать")
    parser.add_argument("--confirm", default="",
                        help="подтверждение вида WRITE-<банк>-<смещение>-<длина>")
    parser.add_argument("--allow-bootloader", action="store_true",
                        help="явно разрешить запись первых двух секторов; без этого "
                             "0x0000…0x1FFF защищены в обоих банках")
    entry = parser.add_mutually_exclusive_group()
    entry.add_argument("--enter", action="store_true",
                       help="самостоятельно выполнить полный вход через 580040:")
    entry.add_argument("--bootloader", action="store_true",
                       help="продолжить вход из recovery bootloader без 580040:")
    parser.add_argument("--readback", nargs=3,
                        metavar=("СМЕЩЕНИЕ", "ДЛИНА", "ФАЙЛ"),
                        help="после записи считать контрольный диапазон выбранного банка")
    parser.add_argument("--recover", action="store_true",
                        help="после записи/read-back выйти через проверенный F1D "
                             "или watchdog из libre recovery; код 2 — нет USB/UART-подтверждения")
    add_flash_read_argument(parser)
    args = parser.parse_args()

    data = args.input.read_bytes()
    if not data:
        raise SystemExit(f"{args.input}: пустой файл")
    if not 0 <= args.address < FLASH_SIZE:
        raise SystemExit(f"адрес вне флеша 0…{FLASH_SIZE - 1:#x}: {args.address:#x}")
    if args.address + len(data) > FLASH_SIZE:
        raise SystemExit("данные выходят за конец флеша")
    bank, offset = divmod(args.address, BANK_SIZE)
    if offset + len(data) > BANK_SIZE:
        raise SystemExit(
            "запись пересекает границу банков; банк выбирается один на прогон — "
            "разбейте на два вызова"
        )
    if offset < BOOTLOADER_AREA.stop and offset + len(data) > BOOTLOADER_AREA.start:
        if not args.allow_bootloader:
            raise SystemExit(
                "отказ: диапазон задевает bootloader 0x0000…0x1FFF; для осознанной "
                "записи первичного загрузчика нужен --allow-bootloader"
            )
    if args.erase:
        if offset % BLOCK_SIZE or len(data) % BLOCK_SIZE:
            raise SystemExit(
                f"--erase стирает секторы целиком, поэтому требует адрес и длину, "
                f"кратные {BLOCK_SIZE:#x}: адрес {offset:#08x}, длина {len(data):#x}"
            )
    elif args.force_dirty:
        print("предупреждение: --force-dirty — биты пойдут только 1 → 0, "
              "проверка будет чтением записанных байт", flush=True)

    readback = None
    if args.readback:
        readback_offset = auto_int(args.readback[0])
        readback_length = auto_int(args.readback[1])
        readback_path = Path(args.readback[2])
        if not 0 <= readback_offset < BANK_SIZE:
            raise SystemExit(f"read-back смещение вне банка: {readback_offset:#x}")
        if readback_length <= 0 or readback_offset + readback_length > BANK_SIZE:
            raise SystemExit("read-back диапазон выходит за границы выбранного банка")
        readback = (readback_offset, readback_length, readback_path)

    expected_token = token(bank, offset, len(data))
    print(f"цель: банк {bank}, {offset:#08x}…{offset + len(data) - 1:#08x} "
          f"({len(data):#x} байт из {args.input})", flush=True)
    if offset < SLOT_AREA.stop and offset + len(data) > SLOT_AREA.start:
        print("ВНИМАНИЕ: диапазон задевает секторы учёта слотов 0x6000…0x7FFF — "
              "там лежат таблицы разделов и маркеры загрузки", flush=True)
    if not args.dry_run and args.confirm != expected_token:
        raise SystemExit(f"для записи нужен --confirm {expected_token}")

    br = Bridge(dry_run=args.dry_run, flash_read_method=args.flash_read_method)
    original_ear = None
    try:
        if args.enter:
            br.enter()
        elif args.bootloader:
            br.enter_bootloader()
        else:
            br.enter_bridge_only()
        preflight(br)
        original_ear = read_ear(br)
        print(f"исходный RDEAR={original_ear:02x}", flush=True)
        if original_ear != bank:
            set_ear(br, bank)
        if readback or args.force_dirty:
            # Reject a required-but-absent 4A extension before any erase/write.
            br.flash_reader()
        arm(br, bank, args.erase)
        if args.erase:
            write_sectors(br, offset, data)
        else:
            write_program(br, offset, data, args.force_dirty)
        if readback:
            readback_offset, readback_length, readback_path = readback
            contents = read_flash(br, readback_offset, readback_length)
            if not br.dry:
                readback_path.parent.mkdir(parents=True, exist_ok=True)
                readback_path.write_bytes(contents)
                print(f"read-back: {readback_length:#x} байт с "
                      f"{readback_offset:#08x} → {readback_path}", flush=True)
        if args.recover:
            recover_stbc(br)
            print("готово; recovery отправлен, UART-транспорт ответил", flush=True)
        else:
            print("готово; скалер оставлен в ISP-режиме", flush=True)
    finally:
        if original_ear is not None and original_ear != bank:
            try:
                set_ear(br, original_ear)
                print(f"RDEAR восстановлен в {original_ear:02x}", flush=True)
            except (IOError, OSError, TimeoutError, RuntimeError) as error:
                print(f"не удалось восстановить RDEAR: {error}", file=sys.stderr)
        br.exit()


if __name__ == "__main__":
    try:
        main()
    except RecoveryVerificationUnavailable as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2) from None
