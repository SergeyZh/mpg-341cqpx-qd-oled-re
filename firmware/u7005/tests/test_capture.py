"""Replay the real MSI updater, with the captured scaler replies at the HAL boundary.

The capture comes from tests/data/update-034.txt plus the MSI FW.034 file
(tools/msi_reference.py); the decoder checks it against the original SHA-256.
"""
import ctypes as C
from collections import deque
from msi_reference import update_packets


def test_complete_msi_update_capture(dev):
    dev.i2c()
    dev.flag('read_override',True)
    group,checked,requests = [],0,0
    pending=deque()
    fixture = (C.c_uint8*8).in_dll(dev.lib,'read_fixture')
    for out, payload in update_packets():
        if out:
            group.append(payload)
            requests+=1
            if payload[1] not in (0xa5,0xa6,0xb6,0xb7,0xbf,0xc0):
                pending.append(group)
                group=[]
        else:
            expected=payload
            current=pending.popleft()
            assert current and expected[1]==current[-1][1]
            fixture[:]=expected[5:13]
            dev.flag('io_ok',expected[2]==1)
            for request in current[:-1]:
                assert dev.report(request) is None
            response=dev.report(current[-1])
            assert response==expected, f'group {checked}: {response.hex()} != {expected.hex()}'
            checked+=1
    # Final A1 commits/reboots the scaler; USB disappears before an IN completion.
    assert not group and len(pending)==1
    assert pending[0]==[bytes.fromhex('04a100000434063c').ljust(64,b'\0')]
    assert requests==52710 and checked==10653
