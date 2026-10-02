import ctypes as C
import random
import struct
from pathlib import Path
import pytest
from msi_reference import aprom

ROOT = Path(__file__).resolve().parents[3]
FAMILIES = ((0xa5, 0xa6, 0xa7), (0xb6, 0xb7, 0xb8), (0xbf, 0xc0, 0xc1))


def table(name, dev):
    return dev.bytes(name, 36)


@pytest.mark.parametrize('name,address', [('msi_uart_lengths', 0x6d98),
    ('msi_i2c_lengths', 0x6dbc), ('msi_read_lengths', 0x6de0)])
def test_tables_against_msi(dev, name, address):
    # Required integration evidence, never silently skipped when missing.
    assert table(name, dev) == aprom()[address:address+36]


@pytest.mark.parametrize('report', [2, 4])
@pytest.mark.parametrize('sub', range(0xa0, 0xc4))
def test_every_table_command(dev, report, sub):
    if report == 4:
        dev.i2c()
    lengths = table('msi_i2c_lengths' if report == 4 else 'msi_uart_lengths', dev)
    reads = table('msi_read_lengths', dev)
    payload = bytes(range(0x30, 0x30+60))
    parts = [sub]
    for family in FAMILIES:
        if sub in family:
            parts = list(family[:family.index(sub)+1])
    expected = b''
    for part in parts:
        response = dev.report(bytes([report, part, 0x6f, 0])+payload)
        expected += payload[:lengths[part-0xa0]]
    if any(sub in f[:2] for f in FAMILIES):
        assert dev.number('writes') == 0 and response is None
    else:
        assert dev.wire == expected
        assert dev.number('writes') == 1
        if report == 4:
            n = reads[sub-0xa0]
            assert response[:4] == bytes([4, sub, 1, 0])
            assert response[4:] == (b'\x6f'+bytes(range(0x30, 0x30+n)) if n else b'').ljust(60, b'\0')
            assert dev.number('write_restart') == (sub in (0xa0, 0xa1))
        else:
            assert response is None and dev.number('uart_port') == 1


@pytest.mark.parametrize('family', FAMILIES)
def test_stream_overflow_and_recovery(dev, family):
    dev.i2c()
    assert dev.report([4, family[1]])[2] == 0
    dev.report(bytes([4, family[0], 0, 0])+b'x'*60)
    for _ in range(69):
        dev.report(bytes([4, family[1], 0, 0])+b'x'*60)
    assert dev.number('writes') == 0
    assert dev.report([4, family[2]])[2] == 0
    dev.report([4, 0xc3])
    assert dev.number('writes') == 1


def test_real_4096_byte_stream(dev):
    dev.i2c()
    # C3 family: 60 + 67*60 + 18 = 4098 wire bytes (SLA,length,data,checksum).
    parts = [0xbf]+[0xc0]*67+[0xc1]
    expected = b''
    rng = random.Random(7005)
    for sub in parts:
        payload = rng.randbytes(60)
        expected += payload[:table('msi_i2c_lengths', dev)[sub-0xa0]]
        dev.report(bytes([4, sub, 0, 0])+payload)
    assert dev.wire == expected and len(expected) == 4098


@pytest.mark.parametrize('sub,n', [(0xa0, 1), (0xa1, 58), (0xb0, 1), (0xb1, 58)])
def test_register_commands(dev, sub, n):
    packet = bytes([3, sub, 0x50, 0x12, n, 0x77])+bytes(range(58))
    answer = dev.report(packet)
    status_offset = 5 if sub in (0xa1, 0xb1) else 4
    assert answer[:4] == packet[:4] and answer[status_offset] == 1
    if sub < 0xb0:
        assert dev.number('write_bus') == 1
        assert dev.wire == b'\xa0\x12'+(b'\x77' if n == 1 else bytes(range(n)))
    else:
        assert dev.number('read_bus') == 1 and dev.number('read_address') == 0x50
        assert answer[status_offset+1:status_offset+1+n] == bytes(range(0x30, 0x30+n))


def test_local_metadata_and_persistence(dev):
    answer = dev.report(b'\x01\xb0'+b'\xa5'*62)
    assert answer[:15] == bytes.fromhex('01 5a 54 a5 15 0000d926 00004f0f 01 01')
    assert answer[15:] == b'\xa5'*49
    assert dev.report(b'\x01\xb2')[1:6] == bytes.fromhex('5a 00126108')
    assert dev.report(b'\x01\xb6\x12\x34\x56\x78')[:6] == bytes.fromhex('01 5a 12345678')
    assert dev.report(b'\x01\xb4')[:6] == bytes.fromhex('01 5a 12345678')
    settings = bytes(range(13))
    assert dev.report(b'\x015b00130'+settings+b'\r')[1:7] == b'5600+\r'
    assert dev.report(b'\x015800130\r')[1:22] == b'5b00130'+settings+b'\r'
    assert dev.report(b'\x01\xd2')[1:12] == b'\xd0b00000001\r'
    packet = bytearray(64); packet[0:2] = b'\x01\xd0'; packet[10] = ord('0')
    assert dev.report(packet)[1:7] == b'\xd0600+\r'
    assert dev.report(b'\x01\xd2')[10] == ord('0')


def test_ascii_events_forwarding_and_uart(dev):
    dev.lib.mock_macro()
    assert dev.report(b'\x01\xc0')[1:12] == b'5b00110001\r'
    assert dev.report(b'\x015800110\r')[1:12] == b'5b00110000\r'
    assert dev.report(b'\x01580040:\r') is None and dev.wire == b'580040:\r'
    reply = b'5b0040:100\r'
    dev.lib.mock_uart(1, reply, len(reply))
    assert dev.bytes('sent', 64) == (b'\x01'+reply).ljust(64, b'\0')
    dev.lib.mock_uart(0, b'5b00;30003\r', 11)
    assert dev.wire == b'5600+\r'
    assert dev.report(b'\x016800;30\r')[1:12] == b'6b00;30003\r'
    dev.lib.mock_uart(0, b'5800;40\r', 8)
    assert dev.wire == b'5b00;40001\r'
    dev.lib.mock_tick(5000)
    dev.lib.mock_uart(0, b'5800;40\r', 8)
    assert dev.wire == b'5b00;40000\r'


def extension(op=1, token=0x1234, offset=0, address=0):
    return struct.pack('<BBBBHHI', 4, 0x4a, 1, op, token, offset, address)


def test_discovery_and_page(dev):
    assert dev.report(b'\x01\xe2')[:12] == b'\x01\x5aU7EX\x01\x4a\x01\x00\x02\x34'
    assert dev.report(extension())[3] == 2
    dev.i2c()
    answer = dev.report(extension(address=0x1000200))
    assert dev.wire == bytes.fromhex('6e044a00020022')
    assert dev.number('reads') == dev.number('writes') == 2
    assert dev.number('delay_total') == 40
    data = bytearray()
    for offset in range(0, 512, 52):
        if offset:
            answer = dev.report(extension(2, offset=offset))
        assert answer[:8] == struct.pack('<BBBBHH', 4, 0x4a, 1, 0, 0x1234, offset)
        assert answer[9] == (offset+52 < 512)
        assert answer[10:12] == b'\x00\x02'
        data.extend(answer[12:12+answer[8]])
    assert data == bytes((i^(i>>8)) & 255 for i in range(512))
    assert dev.number('writes') == 2
    assert dev.report(extension(2, token=9))[3] == 6
    dev.report([4, 0xc3])
    assert dev.report(extension(2))[3] == 5


@pytest.mark.parametrize('address', [1, 511, 0x2000000, 0xffffffff])
def test_invalid_page_addresses(dev, address):
    dev.i2c()
    assert dev.report(extension(address=address))[3] == 1
    assert dev.number('writes') == 0


def test_page_failure_and_reset(dev):
    dev.i2c()
    dev.flag('corrupt', True)
    assert dev.report(extension())[3] == 4
    assert dev.report(extension(2))[3] == 5
    dev.flag('corrupt', False)
    dev.flag('io_ok', False)
    assert dev.report(extension())[3] == 3
    dev.flag('io_ok', True)
    assert dev.report(extension())[3] == 0
    dev.lib.mock_reset()
    assert dev.report(extension(2))[3] == 5


@pytest.mark.parametrize('bad_opcode',[False,True])
def test_page_wire_validation(dev,bad_opcode):
    dev.i2c()
    if bad_opcode:
        C.c_uint8.in_dll(dev.lib,'page_opcode').value=0xb4
    else:
        dev.flag('corrupt_page',True)
    assert dev.report(extension())[3]==4
    assert dev.number('reads')==2
    assert dev.report(extension(2))[3]==5


def test_malformed_and_unknown_packets(dev):
    for n in range(64):
        dev.lib.mock_report(b'\x01\xa0'.ljust(64, b'\0'), n)
    assert dev.number('ldrom_entries') == 0
    assert dev.report([1, 0xff]) is None
    assert dev.report([4, 0xff]) is None
    assert dev.report([3, 0xb1, 0x50, 0, 59]) is None
    assert dev.report([4, 0xc3])[2] == 0  # service UART mode
    assert dev.report([1, 0xa0]) is None
    assert dev.number('ldrom_entries') == 1
