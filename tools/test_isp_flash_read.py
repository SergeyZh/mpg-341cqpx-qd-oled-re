"""Flash-read selection, real 4A framing and compatibility with legacy callers."""

import struct
from unittest.mock import Mock, patch

import pytest

from isp_read import Bridge
from isp_write import read_flash as writer_read_flash
from u7005_flash_read import UnsupportedExtensionError


def contents(address, length):
    return bytes((a + (a >> 9) + 37 * (a >> 24)) & 255
                 for a in range(address, address + length))


class Device:
    def __init__(self):
        self.requests = []
        self.reply = b''
        self.address = 0
        self.status = 0

    def write(self, request):
        assert len(request) == 64
        self.requests.append(request)
        if request[:2] == b'\x01\xe2':
            self.reply = b'\x01\x5aU7EX\x01\x4a\x01\x00\x02\x34'.ljust(64, b'\0')
        else:
            report, command, version, op, token, offset, address = struct.unpack(
                '<BBBBHHI', request[:12])
            assert (report, command, version) == (4, 0x4a, 1)
            if op == 1:
                assert offset == 0 and address % 512 == 0
                self.address = address
            else:
                assert op == 2
            n = min(52, 512 - offset)
            self.reply = (struct.pack('<BBBBHHBBH', 4, 0x4a, 1, self.status,
                                     token, offset, n, offset + n < 512, 512)
                          + contents(self.address + offset, n)).ljust(64, b'\0')
        return 64

    def read(self, length, timeout_ms):
        reply, self.reply = self.reply, b''
        return reply


def bridge(method='auto', bank=0):
    br = Bridge(dry_run=True, flash_read_method=method)
    br.dry = False
    br.dev = Device()
    br.test_bank = bank

    def spi(send, length):
        if send == [0xc8]:
            return bytes([br.test_bank])
        assert send[0] == 0x0b and length <= 249
        address = (br.test_bank << 24) | int.from_bytes(bytes(send[1:4]), 'big')
        return contents(address, length)

    br.spi = Mock(side_effect=spi)
    return br


@pytest.mark.parametrize('bank', [0, 1])
@pytest.mark.parametrize('offset,length', [(0, 512), (511, 515), (0xfffe01, 511)])
def test_fast_read_preserves_bank_relative_api(bank, offset, length):
    br = bridge(bank=bank)
    assert br.read_flash(offset, length) == contents((bank << 24) | offset, length)
    br.spi.assert_called_once_with([0xc8], 1)
    assert br.dev.requests[0][:2] == b'\x01\xe2'


def test_discovery_cached_but_bank_reread_and_writer_uses_same_path():
    br = bridge()
    assert writer_read_flash(br, 5, 600) == contents(5, 600)
    br.test_bank = 1
    assert writer_read_flash(br, 5, 600) == contents(0x1000005, 600)
    assert sum(r[:2] == b'\x01\xe2' for r in br.dev.requests) == 1
    assert br.spi.call_count == 2


@pytest.mark.parametrize('error', [TimeoutError('no E2'), UnsupportedExtensionError('version')])
def test_old_bridge_auto_fallback_is_cached_and_never_sends_4a(error):
    br = bridge(bank=1)
    with patch('isp_read.FlashReader.discover', side_effect=error) as discover:
        for _ in range(2):
            assert br.read_flash(511, 515) == contents(0x10001ff, 515)
        discover.assert_called_once()
    assert not br.dev.requests
    assert all(c.args[0][0] == 0x0b for c in br.spi.call_args_list)


def test_explicit_legacy_does_not_probe_extension():
    br = bridge('legacy')
    assert writer_read_flash(br, 3, 700) == contents(3, 700)
    assert not br.dev.requests
    assert [c.args[1] for c in br.spi.call_args_list] == [249, 249, 202]


def test_forced_4a_after_cached_auto_fallback_cannot_silently_use_legacy():
    br = bridge()
    with patch('isp_read.FlashReader.discover', side_effect=TimeoutError):
        br.read_flash(0, 1)
    br.flash_read_method = '4a'
    br.spi.reset_mock()
    with pytest.raises(UnsupportedExtensionError):
        br.read_flash(0, 1)
    br.spi.assert_not_called()


def test_forced_4a_requires_discovery():
    br = bridge('4a')
    with patch('isp_read.FlashReader.discover', side_effect=TimeoutError):
        with pytest.raises(TimeoutError):
            br.read_flash(0, 1)
    br.spi.assert_not_called()
    assert not br.dev.requests


def test_discovery_transport_error_is_not_hidden_by_fallback():
    br = bridge()
    with patch('isp_read.FlashReader.discover', side_effect=IOError('short HID write')):
        with pytest.raises(IOError, match='short HID'):
            br.read_flash(0, 1)
    br.spi.assert_not_called()


def test_page_error_aborts_without_legacy_retry():
    br = bridge()
    br.dev.status = 4
    with pytest.raises(IOError, match='XOR'):
        br.read_flash(0, 1024)
    br.spi.assert_called_once_with([0xc8], 1)
    assert len(br.dev.requests) == 2  # E2, READ; no FETCH or second page


@pytest.mark.parametrize('offset,length,chunk', [(-1, 1, 249), (0, -1, 249),
                         (0x1000000, 1, 249), (0xffffff, 2, 249), (0, 1, 0)])
def test_bad_ranges_rejected_before_usb(offset, length, chunk):
    br = bridge()
    with pytest.raises(ValueError):
        br.read_flash(offset, length, chunk)
    br.spi.assert_not_called()
    assert not br.dev.requests


def test_zero_length_needs_no_usb():
    br = bridge()
    assert br.read_flash(0, 0) == b''
    br.spi.assert_not_called()
    assert not br.dev.requests


def test_invalid_ear_rejected_before_4a():
    br = bridge(bank=2)
    with pytest.raises(ValueError, match='RDEAR'):
        br.read_flash(0, 1)
    assert len(br.dev.requests) == 1  # discovery only


def test_dry_run_never_opens_extension():
    br = Bridge(dry_run=True, flash_read_method='4a')
    br.spi = Mock(return_value=b'\0' * 4)
    assert br.read_flash(0, 4) == b'\0' * 4
    assert br._flash_reader is None
