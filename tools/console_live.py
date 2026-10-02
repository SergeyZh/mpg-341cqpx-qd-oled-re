#!/usr/bin/env python3
"""Live register experiments through the Leon2 Sub console.

    tools/console_live.py LOG read ADDR...
    tools/console_live.py LOG write ADDR VALUE      # prints old, writes, reads back
    tools/console_live.py LOG lock [N]              # lock indicators, N samples
Every exchange is appended to LOG (raw bytes). A write is refused unless the
console echo of the command matches exactly what was sent.
"""
import sys, time
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent))
import serial
import console_regdump as c

PORT = '/dev/cu.usbmodemflip_Yc4d01'
DELAY = 0.005


def xchg(p, log, cmd):
    text = c.exchange(p, cmd, log, b'DBG >>', 3.0, DELAY)
    echo = text.replace('\r', '').split('\n', 1)[0].strip()
    return text, echo


def rd(p, log, a):
    for _ in range(4):
        text, _ = xchg(p, log, f'mdw 0x{a:08x} 1')
        v = c.parse(text).get(a)
        if v is not None:
            return v
    raise SystemExit(f'read {a:08X} failed')


def wr(p, log, a, v):
    cmd = f'wmem 0x{a:08x} 0x{v:08x}'
    text, echo = xchg(p, log, cmd)
    if echo != cmd:
        raise SystemExit(f'ECHO MISMATCH: sent {cmd!r} console got {echo!r}\n{text!r}')
    return text


def pair(p, log, a):
    return rd(p, log, a) & 0xFF | (rd(p, log, a + 4) & 0xFF) << 8


def lock(p, log):
    ee8 = pair(p, log, 0xCF011EE8)
    d92 = pair(p, log, 0xCF009A48)
    d9a = pair(p, log, 0xCF009A68)
    c484 = pair(p, log, 0xCF00AA10)
    d084 = pair(p, log, 0xCF009A10)
    return f'EE8={ee8} D0:92={d92:04X} D0:9A={d9a:04X} D0:84={d084} C4:84={c484}'


def main():
    log = open(sys.argv[1], 'ab')
    p = serial.Serial(PORT, 115200, timeout=0.05)
    p.reset_input_buffer()
    op = sys.argv[2]
    stamp = time.strftime('%H:%M:%S')
    log.write(f'\n##### {stamp} {" ".join(sys.argv[2:])}\n'.encode())
    if op == 'read':
        for a in sys.argv[3:]:
            a = int(a, 16)
            print(f'{a:08X} = {rd(p, log, a):02X}')
    elif op == 'write':
        a, v = int(sys.argv[3], 16), int(sys.argv[4], 16)
        old = rd(p, log, a)
        wr(p, log, a, v)
        new = rd(p, log, a)
        print(f'{stamp} {a:08X}: {old:02X} -> wrote {v:02X} -> read {new:02X}')
    elif op == 'lock':
        n = int(sys.argv[3]) if len(sys.argv) > 3 else 1
        for i in range(n):
            print(time.strftime('%H:%M:%S'), lock(p, log))
            if i + 1 < n:
                time.sleep(0.5)
    log.write(f'##### end {op}\n'.encode())


if __name__ == '__main__':
    main()
