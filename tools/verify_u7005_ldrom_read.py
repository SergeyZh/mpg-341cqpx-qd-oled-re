#!/usr/bin/env python3
"""Проверка защит считывателя LDROM на модели FMC, без подключения к железу."""
import contextlib
import io
from pathlib import Path
import struct
import tempfile

from pyocd.core.target import Target
import u7005_ldrom_read as reader


class TargetModel:
    def __init__(self, fault=None, running=True):
        self.fault = fault
        self.state = Target.State.RUNNING if running else Target.State.HALTED
        self.regs = {reader.ISPCTL: 0x2A, reader.ISPADDR: 0x1234,
                     reader.ISPDAT: 0xABCDEF, reader.ISPCMD: 0x21,
                     reader.REGLCTL: 0, reader.ISPSTS: 0x100002,
                     reader.ISPTRG: int(fault == 'busy'), reader.DFBA: 0x1F800,
                     0x50000000: reader.PDID}
        self.initial = dict(self.regs)
        self.writes = []
        self.commands = 0

    def get_state(self):
        return self.state

    def halt(self):
        self.state = Target.State.HALTED

    def resume(self):
        self.state = Target.State.RUNNING

    def read_core_register(self, name):
        assert name == 'pc'
        return 0x200030C4

    def read_memory_block8(self, address, size):
        return bytes(size)  # AHB одинаков, физический LDROM ниже отличается.

    def read32(self, address):
        return self.regs[address]

    def write32(self, address, value):
        assert self.state == Target.State.HALTED
        assert address in (reader.ISPCTL, reader.ISPADDR, reader.ISPDAT,
                           reader.ISPCMD, reader.ISPTRG, reader.REGLCTL)
        self.writes.append((address, value))
        if address == reader.REGLCTL:
            self.regs[address] = int(value != 0)
        elif address == reader.ISPCTL:
            self.regs[address] = value & ~reader.ISPFF
            assert value & 2 == self.initial[address] & 2  # BS не меняется.
        elif address == reader.ISPTRG:
            assert value == 1
            assert self.regs[reader.ISPCMD] == reader.CMD_READ
            assert self.regs[reader.ISPCTL] & reader.ISPEN
            assert not self.regs[reader.ISPCTL] & reader.UPDATE_ENABLES
            self.commands += 1
            if self.fault == 'timeout':
                self.regs[address] = 1
            elif self.fault == 'ispff':
                self.regs[reader.ISPCTL] |= reader.ISPFF
            else:
                self.regs[reader.ISPDAT] = self.regs[reader.ISPADDR]
        else:
            self.regs[address] = value


def main():
    for fault, running in ((None, True), (None, False), ('ispff', True),
                           ('busy', True), ('timeout', True)):
        target = TargetModel(fault, running)
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            directory = Path(tmp)
            try:
                result = reader.capture(target, directory)
            except reader.IspError:
                assert fault is not None
            else:
                assert fault is None
                assert result['complete'] and result['registers_restored']
                assert not result['ldrom_equals_aprom_prefix']
                assert (directory / 'ldrom-fmc-a.bin').read_bytes()[:4] == struct.pack('<I', 0x100000)
                assert target.commands == 2 * (1024 + 1024 + 4 + 3)
            if fault in ('busy', 'timeout'):
                assert target.state == Target.State.HALTED
                if fault == 'busy':
                    assert not target.writes
            else:
                assert target.regs == target.initial
                assert target.state == (Target.State.RUNNING if running else Target.State.HALTED)
    print('PASS: FMC READ-only, BS сохранён, два физических чтения, восстановление; '
          'ISPFF, busy и timeout обработаны без запуска записи.')


if __name__ == '__main__':
    main()
