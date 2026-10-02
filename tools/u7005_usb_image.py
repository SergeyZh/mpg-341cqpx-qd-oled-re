#!/usr/bin/env python3
"""Формат установочного USB BIN U7005; только работа с файлами."""
import hashlib
import json
import struct
from pathlib import Path

DFBA = 0x1f800
USB_LENGTH = DFBA - 8
CONFIG = (0xfffffb7e, DFBA, 0xffffff5a)
FORMAT = 'u7005-usb-v1'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def code_info(code):
    if not 208 <= len(code) <= 0x10000 or len(code) % 4:
        raise ValueError('код должен быть кратен 4 и помещаться в первые 64 КиБ')
    stack, reset = struct.unpack_from('<II', code)
    descriptor = struct.unpack_from('<4sIII', code, 192)
    if stack != 0x20005000 or not reset & 1 or not 208 <= (reset & ~1) < len(code):
        raise ValueError('неверные векторы Cortex-M0')
    if descriptor != (b'U7BI', 1, len(code), 1):
        raise ValueError('образ не объявляет поддержку нормализации метаданных USB (U7BI v1)')
    return {'length': len(code), 'sha256': sha(code), 'sum16': sum(code) & 65535}


def prepare(build, backup_path, config_path):
    code = (build / 'u7005-code.bin').read_bytes()
    disk = (build / 'u7005-disk.bin').read_bytes()
    info = code_info(code)
    built = json.loads((build / 'u7005-manifest.json').read_text())
    expected_segments = [
        {'address': 0, 'length': len(code), 'sha256': sha(code)},
        {'address': 0x10000, 'length': len(disk), 'sha256': sha(disk)},
        {'address': USB_LENGTH, 'length': 8,
         'sha256': sha(struct.pack('<II', len(code), info['sum16']))},
    ]
    if (built.get('format') != 'u7005-source-v1' or built.get('segments') != expected_segments
            or built.get('code_length') != len(code) or built.get('ldrom_checksum') != info['sum16']):
        raise ValueError('файлы сборки не совпадают с её manifest; выполните make verify')
    if len(disk) != 44 * 512:
        raise ValueError('виртуальный диск должен занимать 44 сектора')
    backup = backup_path.read_bytes()
    config = config_path.read_bytes()
    if len(config) != 12 or struct.unpack('<III', config) != CONFIG:
        raise ValueError('CONFIG не соответствует исследованному U7005')
    if len(backup) != 0x20000:
        raise ValueError('нужен полный резервный APROM 128 КиБ, включая DataFlash')
    length, checksum = struct.unpack_from('<II', backup, USB_LENGTH)
    if not 0 < length <= USB_LENGTH or (sum(backup[:length]) & 65535) != checksum:
        raise ValueError('резервный APROM не проходит проверку загрузочной суммы')
    image = bytearray(backup[:USB_LENGTH])
    image[:0x10000] = code.ljust(0x10000, b'\xff')
    image[0x10000:0x15800] = disk
    image = bytes(image)
    manifest = {
        'format': FORMAT, 'hardware_tested': False, 'pdid': 0x01205206,
        'ldrom_version': 0x15, 'ldrom_checksum': 0xd926, 'config': list(CONFIG),
        'length': len(image), 'sha256': sha(image), 'sum16': sum(image) & 65535,
        'code': info, 'disk_sha256': sha(disk), 'usb_mode': image[0x1e800],
        'preserved_tail_sha256': sha(image[0x15800:]),
        'backup': {'aprom_sha256': sha(backup), 'config_sha256': sha(config),
                   'dataflash_sha256': sha(backup[DFBA:]),
                   'board_id': struct.unpack_from('<I', backup, DFBA)[0]},
        'normalization': 'first boot: verify full sum, preserve metadata page, replace length/sum with code-only values',
    }
    validate(image, manifest)
    return image, manifest


def validate(image, manifest):
    if not isinstance(manifest, dict):
        raise ValueError('manifest должен быть JSON-объектом')
    if (manifest.get('format') != FORMAT or manifest.get('pdid') != 0x01205206
            or manifest.get('ldrom_version') != 0x15 or manifest.get('ldrom_checksum') != 0xd926
            or manifest.get('config') != list(CONFIG)):
        raise ValueError('неподдерживаемый формат или целевой U7005/LDROM/CONFIG')
    if len(image) != USB_LENGTH or manifest.get('length') != len(image):
        raise ValueError('USB BIN должен содержать ровно [0, 0x1F7F8)')
    if manifest.get('sha256') != sha(image) or manifest.get('sum16') != (sum(image) & 65535):
        raise ValueError('USB BIN не совпал с SHA-256/суммой manifest')
    length = struct.unpack_from('<I', image, 200)[0]
    if not 208 <= length <= 0x10000 or manifest.get('code') != code_info(image[:length]):
        raise ValueError('код USB BIN не совпал с manifest')
    if image[length:0x10000] != b'\xff' * (0x10000-length):
        raise ValueError('между кодом и диском должны быть FF')
    if manifest.get('disk_sha256') != sha(image[0x10000:0x15800]):
        raise ValueError('не совпал виртуальный диск')
    if (manifest.get('usb_mode') != image[0x1e800]
            or manifest.get('preserved_tail_sha256') != sha(image[0x15800:])):
        raise ValueError('не совпали сохранённые области APROM')
    backup = manifest.get('backup', {})
    if not isinstance(backup, dict):
        raise ValueError('нет сведений о резервной копии')
    if not isinstance(backup.get('board_id'), int) or not 0 <= backup['board_id'] <= 0xffffffff:
        raise ValueError('нет board ID резервной копии')
    for name in ('aprom_sha256', 'config_sha256', 'dataflash_sha256'):
        value = backup.get(name, '')
        if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
            raise ValueError(f'неверный backup.{name}')
    return manifest


def load(path):
    path = Path(path)
    image = path.read_bytes()
    manifest = json.loads(path.with_suffix('.json').read_text())
    validate(image, manifest)
    return image, manifest


def write(path, image, manifest):
    validate(image, manifest)
    path = Path(path)
    sidecar = path.with_suffix('.json')
    if path.suffix != '.bin' or path.exists() or sidecar.exists():
        raise ValueError('нужны новые .bin и .json; существующие файлы не перезаписываются')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as f:
        f.write(image)
    with sidecar.open('x') as f:
        json.dump(manifest, f, indent=2)
        f.write('\n')
