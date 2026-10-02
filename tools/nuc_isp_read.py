#!/usr/bin/env python3
"""Читает через SWD то, что у NUC1261 не отображается на шину AHB.

Блок User Configuration (12 байт по 0x300000) прямым чтением не берётся — шина
отвечает FAULT. Он доступен только командой READ контроллера флеша, а её надо
запускать записью в регистры FMC. Тем же способом читаются UID, UCID, CID и PDID.

Запись во флеш исключена аппаратно: в ISPCTL выставляется только ISPEN, а биты
APUEN/LDUEN/SPUEN/CFGUEN остаются нулями — при них контроллер отказывает в
программировании и стирании любого региона. Дополнительно скрипт не пропускает
в ISPCMD ничего, кроме кодов чтения.

Ядро останавливается на время работы. Это не удобство, а требование: прошивка
U7005 сама пользуется FMC (в образе найдены PAGE_ERASE и VECMAP), и если влезть
в его регистры на ходу, можно испортить Data Flash в середине её записи.

Порядок обращений и адреса взяты из BSP Nuvoton, NUC1261BSP,
Library/StdDriver/inc/fmc.h — FMC_Read, FMC_ReadUID, FMC_ReadUCID, FMC_ReadCID,
FMC_ReadPID.

    tools/nuc_isp_read.py                       # всё, что читается
    tools/nuc_isp_read.py --save flash/u7005_config.bin
    tools/nuc_isp_read.py --freq 1000000 --connect under-reset
"""

import argparse
import os
import struct
import sys

FMC = 0x5000C000
ISPCTL, ISPADDR, ISPDAT, ISPCMD, ISPTRG = FMC, FMC + 4, FMC + 8, FMC + 0x0C, FMC + 0x10
DFBA, ISPSTS = FMC + 0x14, FMC + 0x40

REGLCTL = 0x50000100            # SYS_REGLCTL, разблокировка защищённых регистров

ISPEN = 1 << 0                  # единственный бит, который мы ставим
ISPFF = 1 << 6                  # флаг отказа, живёт в ISPCTL

CONFIG_BASE = 0x00300000

CMD_READ, CMD_READ_UID, CMD_READ_CID, CMD_READ_DID = 0x00, 0x04, 0x0B, 0x0C
READ_ONLY_CMDS = {CMD_READ, CMD_READ_UID, CMD_READ_CID, CMD_READ_DID}


class IspError(Exception):
    pass


def unlock_regs(t):
    for key in (0x59, 0x16, 0x88):
        t.write32(REGLCTL, key)
    if t.read32(REGLCTL) != 1:
        raise IspError('SYS_REGLCTL не разблокировался — защищённые регистры недоступны')


def isp_read(t, cmd, addr):
    """Одна команда чтения FMC. Возвращает ISPDAT."""
    if cmd not in READ_ONLY_CMDS:
        raise IspError(f'команда {cmd:#04x} не является командой чтения')
    t.write32(ISPCMD, cmd)
    t.write32(ISPADDR, addr)
    t.write32(ISPDAT, 0)
    t.write32(ISPTRG, 1)
    for _ in range(1000):
        if not (t.read32(ISPTRG) & 1):
            break
    else:
        raise IspError(f'команда {cmd:#04x} по адресу {addr:#x} не завершилась')
    ctl = t.read32(ISPCTL)
    if ctl & ISPFF:
        t.write32(ISPCTL, ctl)       # ISPFF снимается записью единицы
        raise IspError(f'ISPFF: отказ по адресу {addr:#x}')
    return t.read32(ISPDAT)


def decode_config(cfg0, cfg1, cfg2, dfba, ispsts):
    """Разбор блока конфигурации. Метка источника у каждой строки.

    [DS]   — позиция бита есть в datasheets/DS_NUC126_Series_EN_Rev1.05.pdf
    [BSP]  — в заголовках NUC1261BSP
    [ISPT] — полярность подтверждена кодом Nuvoton ISPTool для родственной серии
             (DialogConfiguration_M480.cpp): взведённый бит = функция выключена
    [сем.] — принято по семейству NuMicro, на этом чипе не подтверждено
    """
    cbs_cfg = (cfg0 >> 6) & 3
    cbs_hw = (ispsts >> 1) & 3
    cwdten = ((cfg0 >> 31) & 1) << 2 | ((cfg0 >> 3) & 3)
    boot = {0: 'LDROM + IAP', 1: 'LDROM', 2: 'APROM + IAP', 3: 'APROM'}

    def row(bits, name, value, note, src):
        print(f'    {bits:<8} {name:<7} {value:<7} {note:<34} [{src}]')

    print('  CONFIG0')
    row('[0]', 'DFEN', f'{cfg0 & 1}',
        f'Data Flash {"выключен" if cfg0 & 1 else "включён"}', 'ISPT')
    row('[1]', 'LOCK', f'{(cfg0 >> 1) & 1}',
        f'защита чтения {"снята" if (cfg0 >> 1) & 1 else "ВКЛЮЧЕНА"}', 'ISPT')
    row('[4:3,31]', 'CWDTEN', f'{cwdten:#05b}',
        f'сторожевой таймер {"выключен" if cwdten == 7 else "ВКЛЮЧЁН"}', 'сем.')
    row('[5]', 'MBS', f'{(cfg0 >> 5) & 1}', 'выбор загрузчика', 'BSP')
    row('[7:6]', 'CBS', f'{cbs_cfg:#04b}', f'загрузка: {boot[cbs_cfg]}', 'сем.')
    row('[10]', 'CIOINI', f'{(cfg0 >> 10) & 1}', 'режим выводов после сброса', 'DS')
    row('[20]', 'CBORST', f'{(cfg0 >> 20) & 1}',
        f'сброс по просадке {"выключен" if (cfg0 >> 20) & 1 else "включён"}', 'DS+ISPT')
    row('[22:21]', 'CBOV', f'{(cfg0 >> 21) & 3:#04b}', 'порог детектора просадки', 'DS')
    row('[23]', 'CBODEN', f'{(cfg0 >> 23) & 1}',
        f'детектор просадки {"выключен" if (cfg0 >> 23) & 1 else "включён"}', 'DS+ISPT')
    print('  CONFIG1')
    row('', 'DFBA', f'{cfg1 & 0xFFFFF:#07x}', 'база Data Flash', 'DS')
    print('  CONFIG2')
    alock = cfg2 & 0xFF
    row('[7:0]', 'ALOCK', f'{alock:#04x}',
        'защита снята' if alock == 0x5A else 'ВКЛЮЧЕНА (значение != 0x5A)', 'ISPT')
    if alock == 0x5A and not (cfg0 >> 1) & 1:
        print('    !! ALOCK говорит «снята», а CONFIG0[1] LOCK — «включена»')

    print('\n  Перекрёстные проверки:')
    ok = True
    if (cfg1 & 0xFFFFF) == (dfba & 0xFFFFF):
        print(f'    CONFIG1 == регистр DFBA ({dfba:#010x}) — сходится')
    else:
        print(f'    !! CONFIG1 ({cfg1:#010x}) != регистр DFBA ({dfba:#010x})')
        ok = False
    if cbs_cfg == cbs_hw:
        print(f'    CONFIG0[7:6] == ISPSTS[2:1] ({cbs_hw:#04b}) — раскладка CBS подтверждена')
    else:
        print(f'    !! CONFIG0[7:6]={cbs_cfg:#04b}, а ISPSTS[2:1]={cbs_hw:#04b} — позиция CBS в CONFIG0 угадана неверно')
        ok = False
    if not ok:
        print('    Расхождение означает, что помечённые [сем.] позиции битов к этому чипу\n'
              '    не применимы. Доверять в этом случае только сырым словам выше.')


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--freq', type=int, default=500_000, help='частота SWD, Гц (по умолчанию 500k)')
    ap.add_argument('--connect', default='halt',
                    choices=['halt', 'attach', 'pre-reset', 'under-reset'],
                    help='режим подключения pyOCD')
    ap.add_argument('--probe', help='uid программатора, если их несколько')
    ap.add_argument('--save', metavar='PATH', help='сохранить 12 байт CONFIG сырьём')
    args = ap.parse_args()

    try:
        from pyocd.core.helpers import ConnectHelper
    except ImportError:
        sys.exit('нет pyocd: .venv/bin/pip install pyocd')

    session = ConnectHelper.session_with_chosen_probe(
        unique_id=args.probe, target_override='cortex_m',
        options={'frequency': args.freq, 'connect_mode': args.connect,
                 'resume_on_disconnect': True})
    if session is None:
        sys.exit('программатор не найден')

    with session:
        t = session.target
        t.halt()

        saved_ctl = t.read32(ISPCTL)
        ispsts, dfba = t.read32(ISPSTS), t.read32(DFBA)
        print(f'ISPCTL {saved_ctl:#010x}   ISPSTS {ispsts:#010x}   DFBA {dfba:#010x}')
        print(f'  CBS = {(ispsts >> 1) & 3:#04b}, VECMAP = {ispsts & 0x3FFFFE00:#010x}\n')
        if ispsts & 1:
            sys.exit('FMC занят (ISPBUSY): ядро не остановлено или идёт запись — прервано')

        try:
            unlock_regs(t)
            t.write32(ISPCTL, ISPEN)     # только ISPEN: запись и стирание аппаратно запрещены
            if t.read32(ISPCTL) & 0x3C:
                raise IspError('в ISPCTL остались взведённые *UEN — прервано')

            cfg = [isp_read(t, CMD_READ, CONFIG_BASE + 4 * i) for i in range(3)]
            uid = [isp_read(t, CMD_READ_UID, i << 2) for i in range(3)]
            ucid = [isp_read(t, CMD_READ_UID, 0x10 + 4 * i) for i in range(4)]
            cid = isp_read(t, CMD_READ_CID, 0x00)
            pdid = isp_read(t, CMD_READ_DID, 0x04)
        finally:
            t.write32(ISPCTL, saved_ctl & ~ISPEN)
            t.write32(REGLCTL, 0)        # снова заблокировать защищённые регистры

        print('User Configuration (0x300000, 12 байт)')
        for i, w in enumerate(cfg):
            print(f'  CONFIG{i}  {w:#010x}')
        print()
        decode_config(cfg[0], cfg[1], cfg[2], dfba, ispsts)

        print(f'\nUID   {uid[2]:08x} {uid[1]:08x} {uid[0]:08x}')
        print(f'UCID  {ucid[3]:08x} {ucid[2]:08x} {ucid[1]:08x} {ucid[0]:08x}')
        print(f'CID   {cid:#010x}   (0x000000DA — Nuvoton)')
        print(f'PDID  {pdid:#010x}   (0x01205206 — NUC1261NE4AE)')

        if args.save:
            with open(args.save, 'wb') as f:
                f.write(struct.pack('<3I', *cfg))
            print(f'\nCONFIG записан в {os.path.abspath(args.save)}')


if __name__ == '__main__':
    main()
