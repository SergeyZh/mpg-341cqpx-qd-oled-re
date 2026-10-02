#!/usr/bin/env python3
"""Два чтения LDROM U7005 через FMC, отдельно от отображения памяти на AHB.

Монитор обесточен, CN7003.1 питается внешними 3,3 В; CMSIS-DAP подключён
к CN7003. Ни reset, ни переключения BS/VECMAP, ни команд записи флеша.
Ядро останавливается; его исходное состояние и регистры FMC восстанавливаются.
При незавершённой операции FMC или ошибке восстановления ядро остаётся остановленным.

  .venv/bin/python tools/u7005_ldrom_read.py --out captures/u7005-ldrom-YYYY-MM-DD

Каталог должен быть новым. Исходные flash/u7005_*.bin не заменяются.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import struct

from nuc_isp_read import (CMD_READ, CONFIG_BASE, DFBA, ISPADDR, ISPCMD, ISPDAT,
                          ISPCTL, ISPEN, ISPFF, ISPSTS, ISPTRG, IspError,
                          REGLCTL, isp_read, unlock_regs)

UPDATE_ENABLES = 0x3C
PDID = 0x01205206


def read_fmc_block(target, address, length):
    if address % 4 or length % 4 or length <= 0:
        raise ValueError('адрес и длина должны быть кратны четырём')
    return b''.join(struct.pack('<I', isp_read(target, CMD_READ, a))
                    for a in range(address, address + length, 4))


def capture(target, directory):
    """Не сбрасывать MCU; сохранять BS и состояние остановки от вызывающего кода."""
    from pyocd.core.target import Target

    was_running = target.get_state() == Target.State.RUNNING
    target.halt()
    restored = False
    saved = None
    report = {'utc': datetime.now(timezone.utc).isoformat(), 'files': {},
              'was_running': was_running, 'complete': False}

    def save(name, data):
        (directory / name).write_bytes(data)
        report['files'][name] = {'bytes': len(data),
                                 'sha256': hashlib.sha256(data).hexdigest()}

    try:
        if target.read32(0x50000000) != PDID:
            raise IspError('PDID не совпал с U7005 NUC1261NE4AE')
        if target.read32(ISPTRG) & 1 or target.read32(ISPSTS) & 1:
            raise IspError('FMC занят; регистры не изменены, ядро оставлено остановленным')
        if target.read32(ISPCTL) & ISPFF:
            raise IspError('исходный ISPFF установлен; требуется отдельная диагностика')
        saved = {a: target.read32(a) for a in
                 (ISPCTL, ISPADDR, ISPDAT, ISPCMD, REGLCTL)}
        report['registers_before'] = {f'{a:08x}': f'{v:08x}' for a, v in saved.items()}
        report['ispsts'] = f'{target.read32(ISPSTS):08x}'
        report['dfba'] = f'{target.read32(DFBA):08x}'
        report['pc'] = f'{target.read_core_register("pc"):08x}'
        # Снять AHB до изменения регистров FMC: это наблюдение, не эталон LDROM.
        for tag in ('a', 'b'):
            for name, address in (('ahb-zero', 0), ('ahb-100000', 0x100000)):
                save(f'{name}-{tag}.bin',
                     bytes(target.read_memory_block8(address, 0x1000)))
        unlock_regs(target)
        # BS не меняется даже временно. Командный whitelist в isp_read — второй барьер.
        readonly_ctl = (saved[ISPCTL] & ~(UPDATE_ENABLES | ISPFF)) | ISPEN
        target.write32(ISPCTL, readonly_ctl)
        if target.read32(ISPCTL) != readonly_ctl:
            raise IspError('не удалось выставить FMC в режим чтения')
        for tag in ('a', 'b'):
            for name, address, length in (
                    ('ldrom-fmc', 0x100000, 0x1000),
                    ('aprom-prefix-fmc', 0, 0x1000),
                    ('aprom-metadata-fmc', 0x1F7F0, 16),
                    ('config-fmc', CONFIG_BASE, 12)):
                print(f'{name}-{tag}: {address:#x}+{length:#x}', flush=True)
                save(f'{name}-{tag}.bin', read_fmc_block(target, address, length))
        for name in ('ldrom-fmc', 'aprom-prefix-fmc', 'aprom-metadata-fmc',
                     'config-fmc', 'ahb-zero', 'ahb-100000'):
            if (directory / f'{name}-a.bin').read_bytes() != (directory / f'{name}-b.bin').read_bytes():
                raise IspError(f'два чтения {name} различаются')
        report['ldrom_equals_aprom_prefix'] = (
            (directory / 'ldrom-fmc-a.bin').read_bytes() ==
            (directory / 'aprom-prefix-fmc-a.bin').read_bytes())
        report['complete'] = True
    finally:
        try:
            if saved is not None:
                if target.read32(ISPTRG) & 1 or target.read32(ISPSTS) & 1:
                    raise IspError('FMC не завершился: не восстанавливаем регистры на ходу')
                unlock_regs(target)
                for address in (ISPADDR, ISPDAT, ISPCMD):
                    target.write32(address, saved[address])
                target.write32(ISPCTL, saved[ISPCTL] | ISPFF)  # очистить новый W1C-флаг
                for address in (ISPCTL, ISPADDR, ISPDAT, ISPCMD):
                    if target.read32(address) != saved[address]:
                        raise IspError(f'не восстановлен регистр {address:#x}')
                if not saved[REGLCTL]:
                    target.write32(REGLCTL, 0)
                if target.read32(REGLCTL) != saved[REGLCTL]:
                    raise IspError('не восстановлена блокировка SYS')
                restored = True
        finally:
            report['registers_restored'] = restored
            (directory / 'manifest.json').write_text(
                json.dumps(report, indent=2, ensure_ascii=False) + '\n')
            if restored and was_running:
                target.resume()
            elif not restored:
                print('Ядро оставлено остановленным; см. manifest.json.', flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--freq', type=int, default=500_000)
    parser.add_argument('--probe')
    args = parser.parse_args()
    from pyocd.core.helpers import ConnectHelper

    session = ConnectHelper.session_with_chosen_probe(
        unique_id=args.probe, target_override='cortex_m', blocking=False,
        options={'frequency': args.freq, 'connect_mode': 'attach',
                 'cache.enable_memory': False, 'cache.enable_register': False,
                 'resume_on_disconnect': False})
    if session is None:
        parser.exit(1, 'CMSIS-DAP не найден\n')
    args.out.mkdir(parents=True, exist_ok=False)
    with session:
        report = capture(session.target, args.out)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
