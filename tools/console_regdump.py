#!/usr/bin/env python3
"""Read-only dump of scaler register ranges through a Leon2 console `mdw`.

Only `mdw ADDR N` is ever sent, never `wmem`/`mww`. Intended for the Leon2 Sub
console (CN4008 RX6/TX8, prompt `DBG >>`), which keeps running under both the
stock and the own Main, so the same path reads both states. Every byte of the
exchange goes to the raw log; parsed words go to JSON.

    tools/console_regdump.py --port /dev/cu.X --probe            # one known word
    tools/console_regdump.py --port /dev/cu.X -o DIR/stock       # default ranges
    tools/console_regdump.py --diff DIR/stock.json DIR/own.json  # offline

Default ranges cover the display/FRC path. Auto-increment data ports (OSD and
gamma LUT upload ports CF011780..CF0117BF) are excluded.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import time

DEFAULT_RANGES = [
    (0xCF006800, 0xCF006BFC),  # M/A bank0, display channel status
    (0xCF009800, 0xCF009BFC),  # D bank0: display timing generator
    (0xCF00E800, 0xCF00EFFC),  # engines, gamma control, sync wait, ACE
    (0xCF00F000, 0xCF00F3FC),  # F1C0 and neighbours
    (0xCF011000, 0xCF012FFC),  # FRC channels, post-FRC route/lock, subdivision
]
EXCLUDE = [(0xCF011780, 0xCF0117BC)]  # OSD/gamma LUT data ports
PROBE_ADDRESS = 0xCF03C154  # XDATA F055, documented read in console-commands.md
LINE = re.compile(r'^([0-9A-F]{8}) :(.*)$', re.M)  # 16-byte row, word i in column i


def excluded(address: int) -> bool:
    return any(lo <= address <= hi for lo, hi in EXCLUDE)


def plan(ranges, words_per_command: int):
    """Commands as (address, count); a command never covers an excluded word."""
    commands = []
    for lo, hi in ranges:
        address = lo
        while address <= hi:
            if excluded(address):
                address += 4
                continue
            count = 0
            while (count < words_per_command and address + 4 * count <= hi
                   and not excluded(address + 4 * count)):
                count += 1
            commands.append((address, count))
            address += 4 * count
    return commands


def parse(text: str) -> dict[int, int]:
    words = {}
    for m in LINE.finditer(text.replace('\r', '')):
        base = int(m.group(1), 16)
        for i in range(4):
            cell = m.group(2)[9 * i: 9 * i + 9].strip()
            if re.fullmatch(r'[0-9A-F]{8}', cell):
                words[base + 4 * i] = int(cell, 16)
    return words


def exchange(port, command: str, log, prompt: bytes, limit: float,
             char_delay: float = 0.0) -> str:
    # Under the own Main the Sub console drops input bytes. A damaged
    # `mdw 0x<hex> N` cannot become a write command: it has one m and one w
    # and no e/i/l/r outside hex digits, so neither wmem nor mww can result.
    for byte in command.encode() + b"\r":
        port.write(bytes([byte]))
        if char_delay:
            port.flush()
            time.sleep(char_delay)
    port.flush()
    buf = bytearray()
    start = time.monotonic()
    while time.monotonic() - start < limit:
        chunk = port.read(4096)
        if chunk:
            buf += chunk
            if buf.rstrip().endswith(prompt):
                break
    log.write(buf)
    log.flush()
    return buf.decode("latin-1")


def dump(port, commands, log, prompt: bytes, limit: float,
         char_delay: float = 0.0, retries: int = 0):
    """Read every command; re-send a command while any of its words is missing."""
    values = {}
    missing = []
    resent = 0
    for address, count in commands:
        wanted = [address + 4 * i for i in range(count)]
        for attempt in range(retries + 1):
            resent += attempt > 0
            got = parse(exchange(port, f"mdw 0x{address:08x} {count}", log, prompt,
                                 limit, char_delay))
            values.update({a: got[a] for a in wanted if a in got})
            if all(a in values for a in wanted):
                break
        missing += [a for a in wanted if a not in values]
    return values, missing, resent


def diff(left: Path, right: Path) -> int:
    a = {int(k, 16): v for k, v in json.loads(left.read_text())["words"].items()}
    b = {int(k, 16): v for k, v in json.loads(right.read_text())["words"].items()}
    common = sorted(set(a) & set(b))
    changed = [x for x in common if a[x] != b[x]]
    print(f"common {len(common)}, differ {len(changed)}, "
          f"only-left {len(set(a) - set(b))}, only-right {len(set(b) - set(a))}")
    for x in changed:
        print(f"{x:08X} XDATA {(x - 0xCF000000) // 4:04X}: "
              f"{a[x]:08X} -> {b[x]:08X}  xor {a[x] ^ b[x]:08X}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", help="explicit serial device")
    ap.add_argument("-o", "--output", type=Path, help="output prefix: .log/.json")
    ap.add_argument("--probe", action="store_true", help=f"read only {PROBE_ADDRESS:08X}")
    ap.add_argument("--range", action="append", default=[],
                    help="HEXLO-HEXHI inclusive word range instead of defaults")
    ap.add_argument("--exclude", action="append", default=[],
                    help="HEXLO-HEXHI inclusive word range never read (adds to built-ins)")
    ap.add_argument("--words", type=int, default=4, help="words per mdw command")
    ap.add_argument("--prompt", default="DBG >>")
    ap.add_argument("--limit", type=float, default=3.0, help="seconds per command")
    ap.add_argument("--char-delay", type=float, default=0.0, help="seconds between sent bytes")
    ap.add_argument("--retries", type=int, default=3, help="re-sends of an incomplete command")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--diff", nargs=2, type=Path, metavar=("LEFT", "RIGHT"))
    args = ap.parse_args()

    if args.diff:
        return diff(*args.diff)
    EXCLUDE.extend(tuple(int(x, 16) for x in r.split("-")) for r in args.exclude)
    ranges = [(PROBE_ADDRESS, PROBE_ADDRESS)] if args.probe else (
        [tuple(int(x, 16) for x in r.split("-")) for r in args.range] or DEFAULT_RANGES)
    commands = plan(ranges, 1 if args.probe else args.words)
    total = sum(c for _, c in commands)
    print(f"{len(commands)} commands, {total} words")
    if args.dry_run:
        return 0
    if not args.port or not args.output:
        ap.error("--port and --output are required to read")
    for suffix in (".log", ".json"):
        if args.output.with_suffix(suffix).exists():
            ap.error(f"{args.output.with_suffix(suffix)} exists")

    import serial
    port = serial.Serial(args.port, 115200, timeout=0.05)
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    t0 = time.monotonic()
    with args.output.with_suffix(".log").open("xb") as log:
        port.reset_input_buffer()
        values, missing, resent = dump(port, commands, log, args.prompt.encode(),
                                       args.limit, args.char_delay, args.retries)
    port.close()
    raw = args.output.with_suffix(".log").read_bytes()
    result = {
        "format": "console-regdump-v1",
        "port": args.port,
        "started_utc": started,
        "elapsed_seconds": round(time.monotonic() - t0, 3),
        "ranges": [f"{lo:08X}-{hi:08X}" for lo, hi in ranges],
        "excluded": [f"{lo:08X}-{hi:08X}" for lo, hi in EXCLUDE],
        "commands_sent": [f"mdw 0x{a:08x} {c}" for a, c in commands][:3] + ["..."],
        "writes_sent": 0,
        "char_delay": args.char_delay,
        "commands_resent": resent,
        "words_requested": total,
        "words_parsed": len(values),
        "missing": [f"{a:08X}" for a in missing],
        "log_sha256": hashlib.sha256(raw).hexdigest(),
        "words": {f"{a:08X}": v for a, v in sorted(values.items())},
    }
    args.output.with_suffix(".json").open("x").write(json.dumps(result, indent=1) + "\n")
    print(f"parsed {len(values)}/{total}, missing {len(missing)}, resent {resent}, "
          f"{result['elapsed_seconds']} s")
    if args.probe and values:
        print(f"{PROBE_ADDRESS:08X} = {values[PROBE_ADDRESS]:08X}")
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
