#!/usr/bin/env python3
"""Проверка адресов, векторов, RAM-кода FMC и метаданных готовой сборки."""
import json
import subprocess
import struct
import sys
from pathlib import Path
from elftools.elf.elffile import ELFFile
from package import package, intel_hex
from msi_reference import aprom

build = Path(sys.argv[1])
code = (build/'u7005-code.bin').read_bytes()
segments, manifest = package(code)
assert (build/'u7005.hex').read_text() == intel_hex(segments)
assert json.loads((build/'u7005-manifest.json').read_text()) == manifest
with (build/'u7005.elf').open('rb') as f:
    elf = ELFFile(f)
    assert elf['e_machine'] == 'EM_ARM' and elf.little_endian
    symbols = {s.name: s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols()}
    assert symbols['_code_end'] == len(code)
    assert symbols['image_info'] == 192
    assert struct.unpack_from('<4sIII',code,192) == (b'U7BI',1,len(code),1)
    assert 0x20000000 <= symbols['fmc_command'] < 0x20005000
    assert symbols['_bss_end'] <= symbols['_stack_top']-2048
    ramfunc=elf.get_section_by_name('.ramfunc')
    data=elf.get_section_by_name('.data')
    assert ramfunc['sh_addr']+ramfunc['sh_size']==data['sh_addr']
    for index, name in {1:'Reset_Handler', 15:'SysTick_Handler', 20:'GPAB_IRQHandler',
                        28:'UART02_IRQHandler', 29:'UART1_IRQHandler', 39:'USBD_IRQHandler'}.items():
        assert struct.unpack_from('<I', code, index*4)[0] == symbols[name] | 1
    # Every executable section is in the application or SRAM, never the disk/DF/LDROM.
    for sec in elf.iter_sections():
        if sec['sh_flags'] & 4 and sec['sh_size']:
            a, n = sec['sh_addr'], sec['sh_size']
            assert 0 <= a < a+n <= 0x10000 or 0x20000000 <= a < a+n <= 0x20005000
    root=Path(__file__).resolve().parents[3]
    stock=aprom()
    symtab=elf.get_section_by_name('.symtab')
    for name,address in {'device':0x6c57,'reports':0x6bf8,'hid_config':0x6c7b,
                         'composite_config':0x6ca4,'product':0x6cf0,'serial':0x6d1c,'vendor':0x6ce8}.items():
        sym=symtab.get_symbol_by_name(name)[0]
        sec=elf.get_section(sym['st_shndx'])
        start=sym['st_value']-sec['sh_addr']
        assert sec.data()[start:start+sym['st_size']]==stock[address:address+sym['st_size']],name
    listing=subprocess.check_output([str(root/'tools/u7005-env.sh'),'arm-none-eabi-objdump',
                                    '-d','--section=.ramfunc',str(build/'u7005.elf')],text=True)
    # The SRAM routine is a leaf; its literal pool resides in the same SRAM section.
    assert '\tbl\t' not in listing and '\tblx\t' not in listing
print('ELF/HEX: vectors, FMC in SRAM, >=2 KiB stack, protected ranges, checksum OK')
