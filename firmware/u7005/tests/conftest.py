import ctypes as C
import subprocess
import sys
from pathlib import Path
import pytest

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT/'tools'))  # msi_reference for every test module


@pytest.fixture(scope='session')
def library(tmp_path_factory):
    dest = tmp_path_factory.mktemp('native')/'bridge.dylib'
    subprocess.run(['cc', '-shared', '-fPIC', '-std=c11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                    '-I'+str(PROJECT/'include'), str(PROJECT/'src/bridge.c'), str(PROJECT/'src/msc.c'),
                    str(PROJECT/'tests/mock.c'), '-o', str(dest)], check=True)
    lib = C.CDLL(str(dest))
    lib.mock_report.argtypes = [C.c_char_p, C.c_size_t]
    lib.mock_uart.argtypes = [C.c_uint, C.c_char_p, C.c_size_t]
    lib.msc_out.argtypes = [C.c_char_p, C.c_size_t]
    lib.msc_in.argtypes = [C.c_void_p]
    lib.msc_in.restype = C.c_size_t
    lib.msc_in_pending.restype = lib.msc_halted.restype = C.c_bool
    return lib


class Device:
    def __init__(self, lib):
        self.lib = lib
        lib.mock_init()

    def number(self, name):
        return C.c_uint.in_dll(self.lib, name).value

    def bytes(self, name, n):
        return bytes((C.c_uint8*n).in_dll(self.lib, name))

    def flag(self, name, value):
        C.c_bool.in_dll(self.lib, name).value = value

    def report(self, data):
        data = bytes(data).ljust(64, b'\0')
        count = self.number('sends')
        self.lib.mock_report(data, len(data))
        return self.bytes('sent', 64) if count != self.number('sends') else None

    def i2c(self):
        assert self.report(b'\x01\xe0\x01')[:3] == b'\x01\x5a\x01'

    @property
    def wire(self):
        return self.bytes('wire', self.number('wire_length'))


@pytest.fixture
def dev(library):
    return Device(library)
