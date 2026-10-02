"""Actual C boot policy with a simulated word-readable flash and page writer."""
import ctypes as C
import struct
import subprocess
import pytest
from conftest import PROJECT

META = 0x1f7f8
READ = C.CFUNCTYPE(C.c_bool, C.c_uint32, C.POINTER(C.c_uint32))
WRITE = C.CFUNCTYPE(C.c_bool, C.POINTER(C.c_uint32))


@pytest.fixture(scope='session')
def bootlib(tmp_path_factory):
    path = tmp_path_factory.mktemp('boot')/'boot.dylib'
    subprocess.run(['cc', '-shared', '-fPIC', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                    '-I'+str(PROJECT/'include'), str(PROJECT/'src/boot_metadata.c'), '-o', str(path)], check=True)
    lib = C.CDLL(str(path))
    lib.boot_metadata_prepare.argtypes = [C.c_uint32, READ, WRITE]
    lib.boot_metadata_prepare.restype = C.c_bool
    return lib


class Flash:
    def __init__(self, length=256):
        self.code_length = length
        self.data = bytearray((i*7+3) & 255 for i in range(0x20000))
        struct.pack_into('<II', self.data, META, META, sum(self.data[:META]) & 65535)
        self.reads, self.writes = [], []
        self.read_error = None
        self.write_failure = False
        self.corrupt_readback = False

    def prepare(self, lib):
        def read(address, output):
            self.reads.append(address)
            if address == self.read_error:
                return False
            output[0] = struct.unpack_from('<I', self.data, address)[0]
            return True

        def write(words):
            self.writes.append(tuple(words[i] for i in range(2)))
            if self.write_failure:
                return False
            struct.pack_into('<II', self.data, META, *self.writes[-1])
            if self.corrupt_readback:
                self.data[META+4] ^= 1
            return True

        return lib.boot_metadata_prepare(self.code_length, READ(read), WRITE(write))


def test_normalizes_once_preserving_every_other_byte(bootlib):
    flash = Flash()
    before = bytes(flash.data)
    assert flash.prepare(bootlib)
    assert flash.writes == [(256, sum(before[:256]) & 65535)]
    assert flash.data[:META] == before[:META] and flash.data[META+8:] == before[META+8:]
    # Ordinary boots may change both mutable regions without forcing ISP or more erases.
    flash.data[0x10000] ^= 1
    flash.data[0x1e800] ^= 1
    assert flash.prepare(bootlib) and len(flash.writes) == 1
    flash.data[200] ^= 1
    assert not flash.prepare(bootlib) and len(flash.writes) == 1


@pytest.mark.parametrize('where', [0, 252, 0x10000, 0x1e800, 0x1f7f4, META, META+4])
def test_corruption_before_normalization_never_gets_blessed(bootlib, where):
    flash = Flash()
    flash.data[where] ^= 1
    assert not flash.prepare(bootlib)
    assert not flash.writes


@pytest.mark.parametrize('length', [0, 4, 192, 209, 0x10004, 0xffffffff])
def test_invalid_linked_length_does_not_read_or_write(bootlib, length):
    flash = Flash(length)
    assert not flash.prepare(bootlib)
    assert not flash.reads and not flash.writes


@pytest.mark.parametrize('length,checksum', [(0, 0), (0x10000, 0), (META-4, 0), (0xffffffff, 0xffffffff)])
def test_unexpected_or_erased_metadata_is_rejected(bootlib, length, checksum):
    flash = Flash()
    struct.pack_into('<II', flash.data, META, length, checksum)
    assert not flash.prepare(bootlib) and not flash.writes


@pytest.mark.parametrize('where', [0, 128, 0x10000, META, META+4])
def test_fmc_read_error_aborts(bootlib, where):
    flash = Flash()
    flash.read_error = where
    assert not flash.prepare(bootlib) and not flash.writes


@pytest.mark.parametrize('failure', ['write_failure', 'corrupt_readback'])
def test_failed_metadata_commit_prevents_application_start(bootlib, failure):
    flash = Flash()
    setattr(flash, failure, True)
    assert not flash.prepare(bootlib)
    assert len(flash.writes) == 1


def test_word_boundary_power_loss_model_leaves_boot_metadata_invalid():
    # board.c writes the preserved 2-KiB page in ascending word order, checksum last.
    # This models completed FMC word operations, not partial physical erase/program.
    page = bytes((i*11) & 255 for i in range(2040)) + struct.pack('<II', 256, 12345)
    for words in range(512):
        interrupted = page[:4*words] + b'\xff'*(2048-4*words)
        assert struct.unpack_from('<I', interrupted, 2044)[0] == 0xffffffff
