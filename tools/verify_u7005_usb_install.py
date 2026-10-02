#!/usr/bin/env python3
"""Аудит резервных копий и модели USB A0 у LDROM 15; без доступа к устройству.

Модель следует листингу LDROM 1EC/49C/59C/5D8/D5A. Это не эмуляция ARM
и не проверка физического программирования. Выходные BIN для прошивки не создаёт.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path
from u7005_usb_image import code_info

ROOT = Path(__file__).resolve().parents[1]
DFBA = 0x1f800
META = DFBA-8


def sha(data):
    return hashlib.sha256(data).hexdigest()


def boot_target(aprom, cpu_reset=False):
    """Решение уже запущенного LDROM; CPU reset сам по себе не выбирает BS=1."""
    if cpu_reset:
        return 'ISP'
    length, checksum = struct.unpack_from('<II',aprom,META)
    if length > len(aprom) or (sum(aprom[:length]) & 65535) != checksum:
        return 'ISP'
    return 'APROM'


def usb_update(original, image):
    """Успешная последовательность A0/00, без FF, A1, A3, C3."""
    assert 0 < len(image) <= META and len(image)%4 == 0
    aprom = bytearray(original)
    erased = []
    for base in range(0,DFBA,0x800):
        aprom[base:base+0x800] = b'\xff'*0x800
        erased.append(base)
    offset, blocks = 0,0
    while offset < len(image):
        count = min(48 if not blocks else 56,len(image)-offset)
        assert count%4 == 0
        aprom[offset:offset+count] = image[offset:offset+count]
        offset += count
        blocks += 1
    checksum = sum(image)&65535
    struct.pack_into('<II',aprom,META,len(image),checksum)
    assert aprom[DFBA:] == original[DFBA:]
    return aprom, erased, blocks


def audit(root, code_path, disk_path):
    aprom = (root/'flash/u7005_aprom.bin').read_bytes()
    config = (root/'flash/u7005_config.bin').read_bytes()
    ldrom = (root/'flash/u7005_ldrom_fmc.bin').read_bytes()
    sprom = (root/'flash/u7005_sprom.bin').read_bytes()
    assert len(aprom)==0x20000 and len(config)==12 and len(ldrom)==4096 and len(sprom)==2048
    assert sha(aprom)=='1b89385ed35d472d7f840325c7e6dee952510c53d364c854b383c3e4296d55cb'
    assert sha(ldrom)=='adf83bc017642eb676b40d746a5de30fb3206be70d3d162e7f6e7dfa55e1e330'
    assert struct.unpack('<III',config)==(0xfffffb7e,DFBA,0xffffff5a)
    assert struct.unpack_from('<III',ldrom,0xff4)==(0x15,0xfec,0xd926)
    assert sum(ldrom[:0xfec])&65535==0xd926
    assert boot_target(aprom)=='APROM'
    evidence = root/'captures/u7005-ldrom-2026-09-13-fmc'
    manifest = json.loads((evidence/'manifest.json').read_text())
    for name,expected in manifest['files'].items():
        data=(evidence/name).read_bytes()
        assert len(data)==expected['bytes'] and sha(data)==expected['sha256'],name
    for suffix in ('a','b'):
        assert ldrom==(evidence/f'ldrom-fmc-{suffix}.bin').read_bytes()
        assert config==(evidence/f'config-fmc-{suffix}.bin').read_bytes()
        assert aprom[:4096]==(evidence/f'aprom-prefix-fmc-{suffix}.bin').read_bytes()
        assert aprom[0x1f7f0:DFBA]==(evidence/f'aprom-metadata-fmc-{suffix}.bin').read_bytes()
    usb = json.loads((root/'captures/u7005-ldrom-usb-probe-2026-09-13/result.json').read_text())
    assert usb['complete'] and usb['before']==usb['after']
    assert usb['before']['board_id']==struct.unpack_from('<I',aprom,DFBA)[0]
    code,disk=code_path.read_bytes(),disk_path.read_bytes()
    code_info(code)
    assert 192<len(code)<=0x10000 and len(disk)==44*512
    code_only,erased,short_blocks=usb_update(aprom,code)
    assert len(erased)==63 and erased[-1]==0x1f000
    assert code_only[0x10000:0x15800]==b'\xff'*len(disk)
    assert code_only[0x1e800]==255
    assert boot_target(code_only)=='APROM'  # Checksum is valid, resources are missing.
    full=bytearray(aprom[:META])
    full[:0x10000]=b'\xff'*0x10000
    full[:len(code)]=code
    full[0x10000:0x15800]=disk
    installed,_,blocks=usb_update(aprom,full)
    assert installed[0x1e800:0x1f000]==aprom[0x1e800:0x1f000]
    assert boot_target(installed)=='APROM'
    transitions={}
    for name,address in [('usb_mode',0x1e800),('virtual_disk',0x10000)]:
        changed=bytearray(installed)
        changed[address]^=1
        assert boot_target(changed)=='ISP'
        transitions[name]='ISP after a one-bit mutation inside the installed checksum range'
    # Model of normalization; the actual C implementation is tested by test_boot_metadata.py.
    normalized=bytearray(installed)
    struct.pack_into('<II',normalized,META,len(code),sum(code)&65535)
    assert boot_target(normalized)=='APROM'
    normalized[0x1e800]^=1
    normalized[0x10000]^=1
    assert boot_target(normalized)=='APROM'
    normalized[200]^=1
    assert boot_target(normalized)=='ISP'
    incomplete=bytearray(installed)
    incomplete[META:DFBA]=b'\xff'*8
    assert boot_target(incomplete)=='ISP'
    # Valid checksum says nothing about whether the application can enumerate USB.
    assert boot_target(installed,cpu_reset=False)=='APROM'
    assert boot_target(installed,cpu_reset=True)=='ISP'
    result={
        'hardware_access':False,'method':'Ghidra review + Python model, not ARM emulation',
        'backups':{name:{'size':len(data),'sha256':sha(data)} for name,data in
                   [('aprom',aprom),('dataflash',aprom[DFBA:]),('config',config),('physical_ldrom',ldrom),('sprom',sprom)]},
        'saved_usb_mode':aprom[0x1e800],
        'code':{'size':len(code),'sha256':sha(code),'sum16':sum(code)&65535},
        'erase_pages':len(erased),'erase_end_exclusive':DFBA,
        'code_only_usb':{'packets':short_blocks,'boot':boot_target(code_only),'disk_missing':True,'usb_mode':255},
        'full_usb':{'size':len(full),'packets':blocks,'sum16':sum(full)&65535,'boot':boot_target(installed),
                    'dataflash_preserved':True,'mode_preserved':True,'after_mutation':transitions},
        'normalization_excludes_mutable_regions':True,
        'normalization_declared_by_image_descriptor':True,
        'erased_metadata_boot':'ISP',
        'valid_checksum_broken_usb_app':'APROM; checksum alone cannot detect a broken USB stack',
        'current_hardware_state_verified':False,
    }
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=ROOT)
    p.add_argument('--code',type=Path,default=ROOT/'out/u7005/u7005-code.bin')
    p.add_argument('--disk',type=Path,default=ROOT/'out/u7005/u7005-disk.bin')
    p.add_argument('--out',type=Path)
    a=p.parse_args()
    result=audit(a.root,a.code,a.disk)
    text=json.dumps(result,indent=2)+'\n'
    if a.out:
        a.out.write_text(text)
    print(text,end='')


if __name__=='__main__':
    main()
