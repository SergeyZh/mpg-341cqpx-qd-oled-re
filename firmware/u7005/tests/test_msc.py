import ctypes as C
import struct
import pytest


def cbw(cdb, length=0, incoming=True):
    return b'USBC'+b'TEST'+struct.pack('<I', length)+bytes([0x80 if incoming else 0, 0, len(cdb)])+bytes(cdb).ljust(16, b'\0')


def start(dev, cdb, length=0, incoming=True):
    p = cbw(cdb, length, incoming)
    dev.lib.msc_out(p, len(p))


def collect(dev):
    packets = []
    for _ in range(400):
        if not dev.lib.msc_in_pending():
            return packets
        buf = C.create_string_buffer(64)
        n = dev.lib.msc_in(buf)
        packets.append(buf.raw[:n])
    raise AssertionError('MSC did not finish')


@pytest.mark.parametrize('op,cdb_length', [(0,6), (0x1b,6), (0x1e,6), (0x2f,10), (0x35,10)])
def test_no_data_commands(dev, op, cdb_length):
    start(dev, bytes([op])+bytes(cdb_length-1))
    assert collect(dev) == [b'USBSTEST'+bytes(5)]


@pytest.mark.parametrize('op,size,cdb', [(0x12,36, b'\0\0\0\x24\0'),
    (3,18,b'\0\0\0\x12\0'), (0x1a,4,b'\0\x3f\0\x04\0'),
    (0x5a,8, b'\0\x3f\0\0\0\0\0\x08\0'),
    (0x23,12,bytes(7)+b'\x0c\0'), (0x25,8,bytes(9)),
    (0x9e,32,b'\x10'+bytes(11)+b'\x20\0\0')])
def test_scsi_replies(dev, op, size, cdb):
    start(dev, bytes([op])+cdb, size)
    packets = collect(dev)
    assert len(packets) == 2 and len(packets[0]) == size
    assert packets[-1] == b'USBSTEST'+bytes(5)
    if op == 0x25:
        assert packets[0] == struct.pack('>II', 43, 512)


@pytest.mark.parametrize('large', [False, True])
def test_disk_write_read_last_sector(dev, large):
    def cdb(op):
        return bytes([op, 0])+struct.pack('>I', 43)+(struct.pack('>I', 1)+bytes(2) if large else b'\0\0\x01\0')
    start(dev, cdb(0xaa if large else 0x2a), 512, False)
    page = bytes(range(256))*2
    for offset in range(0,512,64):
        dev.lib.msc_out(page[offset:offset+64],64)
    assert collect(dev) == [b'USBSTEST'+bytes(5)]
    start(dev, cdb(0xa8 if large else 0x28),512)
    packets = collect(dev)
    assert b''.join(packets[:-1]) == page
    assert packets[-1][-5:] == bytes(5)


def test_range_failure_sense_and_residue(dev):
    start(dev, b'\x28\0'+struct.pack('>I',44)+b'\0\0\x01\0',512)
    packets = collect(dev)
    assert packets == [b'', b'USBSTEST'+struct.pack('<I',512)+b'\x01']
    start(dev,b'\x03\0\0\0\x12\0',18)
    reply = collect(dev)[0]
    assert reply[2] == 5 and reply[12] == 0x21


def test_invalid_cbw_requires_reset(dev):
    dev.lib.msc_out(b'x'*31,31)
    assert dev.lib.msc_halted()
    start(dev, bytes(6))
    assert not collect(dev)
    dev.lib.msc_reset()
    start(dev, bytes(6))
    assert collect(dev)[0][-1] == 0


def test_phase_error(dev):
    start(dev, b'\x25'+bytes(9),4)
    packets = collect(dev)
    assert len(packets[0]) == 4 and packets[-1][-1] == 2
    assert dev.lib.msc_halted()


@pytest.mark.parametrize('cdb', [b'\x15\0\0\0\x08\0', b'\x55'+bytes(7)+b'\x08\0'])
def test_mode_select(dev,cdb):
    start(dev,cdb,8,False)
    dev.lib.msc_out(bytes(8),8)
    assert collect(dev)[0][-5:] == bytes(5)
