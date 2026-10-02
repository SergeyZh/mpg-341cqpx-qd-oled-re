import sys
import pytest
from test_bridge import ROOT
sys.path.insert(0,str(ROOT/'tools'))
from u7005_flash_read import FlashReader


class Transport:
    def __init__(self,dev):
        self.dev,self.reply=dev,[]
    def write(self,data):
        r=self.dev.report(data)
        if r:
            self.reply.append(r)
        return len(data)
    def read(self,n,timeout_ms):
        return self.reply.pop(0) if self.reply else b''


def test_host_reads_real_c_firmware(dev):
    reader=FlashReader(Transport(dev))
    with pytest.raises(RuntimeError):
        reader.page(0)
    assert dev.number('writes')==0
    reader.discover()
    dev.i2c()
    page=bytes((i^(i>>8)) & 255 for i in range(512))
    assert b''.join(reader.read(511,515))==page[-1:]+page+page[:2]
    assert dev.number('writes')==6
    dev.flag('corrupt',True)
    with pytest.raises(IOError,match='XOR'):
        reader.page(0)


@pytest.mark.parametrize('a,n', [(0,0),(-1,1),(0,0x2000001),(0x2000000,1)])
def test_host_bounds_before_io(dev,a,n):
    reader=FlashReader(Transport(dev))
    with pytest.raises(ValueError):
        list(reader.read(a,n))
    assert dev.number('sends')==0
