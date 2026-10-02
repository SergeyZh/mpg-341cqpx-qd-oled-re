import struct
import sys
from conftest import PROJECT
sys.path.insert(0,str(PROJECT/'tools'))
from package import disk_image, package, intel_hex


def test_fat12_and_sparse_hex():
    disk=disk_image()
    assert len(disk)==44*512 and disk[510:512]==b'\x55\xaa'
    assert struct.unpack_from('<HBHBHH',disk,11)==(512,1,1,2,16,44)
    assert disk[512:1024]==disk[1024:1536]
    assert disk[1536:1547]==b'MSI     URL'
    assert struct.unpack_from('<H',disk,1536+26)[0]==2
    size=struct.unpack_from('<I',disk,1536+28)[0]
    assert disk[2048:2048+size].startswith(b'[InternetShortcut]\r\nURL=https://')
    code=struct.pack('<II',0x20005000,193)+bytes(192)
    segments,manifest=package(code)
    assert segments[-1]==(0x1f7f8,struct.pack('<II',len(code),sum(code)&65535))
    upper=0; loaded={}
    for line in intel_hex(segments).splitlines():
        record=bytes.fromhex(line[1:]); assert sum(record)&255==0
        size,address,kind=record[0],int.from_bytes(record[1:3],'big'),record[3]
        payload=record[4:-1]; assert size==len(payload)
        if kind==4:
            upper=int.from_bytes(payload,'big')<<16
        elif kind==0:
            for offset,byte in enumerate(payload): loaded[upper+address+offset]=byte
    assert len(loaded)==len(code)+44*512+8
    assert all(a<0x15800 or 0x1f7f8<=a<0x1f800 for a in loaded)
    assert manifest['hardware_tested'] is False
