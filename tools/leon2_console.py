#!/usr/bin/env python3
"""Консоль отладочных UART монитора (CN4008) через USB-UART мост.

Строка у всех трёх консолей принимается только по `\r`; ответ читается до тишины,
а не до приглашения — у Leon2 Sub приглашение печатается не всегда.

    tools/leon2_console.py --listen 5                 # слушать эфир
    tools/leon2_console.py "mem 0xA8030000"           # одна команда
    tools/leon2_console.py -f cmds.txt --log out.log  # пачка команд из файла

Порт по умолчанию — первый /dev/cu.usbmodem*, скорость 115200 (Leon2 и Tensilica;
у 8051 — 4800, но у него нет приёма).
"""
import argparse
import glob
import sys
import time

import serial


def open_port(dev, baud):
    if dev is None:
        cands = sorted(glob.glob("/dev/cu.usbmodem*"))
        if not cands:
            sys.exit("не найден /dev/cu.usbmodem*")
        dev = cands[0]
    return serial.Serial(dev, baud, timeout=0.05)


def drain(port, quiet=0.35, limit=6.0):
    """Читать до тишины в `quiet` секунд или до `limit` всего."""
    buf = bytearray()
    start = time.monotonic()
    last = start
    while time.monotonic() - start < limit:
        chunk = port.read(4096)
        if chunk:
            buf += chunk
            last = time.monotonic()
        elif time.monotonic() - last > quiet:
            break
    return bytes(buf)


def send(port, cmd, quiet, limit):
    port.reset_input_buffer()
    port.write(cmd.encode() + b"\r")
    port.flush()
    return drain(port, quiet, limit)


def show(data):
    return data.decode("latin-1").replace("\r\n", "\n").replace("\r", "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmds", nargs="*", help="команды для отправки")
    ap.add_argument("-p", "--port")
    ap.add_argument("-b", "--baud", type=int, default=115200)
    ap.add_argument("-f", "--file", help="файл с командами, по одной в строке")
    ap.add_argument("--listen", type=float, metavar="SEC", help="только слушать")
    ap.add_argument("--quiet", type=float, default=0.35, help="порог тишины, с")
    ap.add_argument("--limit", type=float, default=6.0, help="потолок ожидания, с")
    ap.add_argument("--delay", type=float, default=0.15, help="пауза между командами")
    ap.add_argument("--log", help="дописывать весь обмен сюда")
    args = ap.parse_args()

    port = open_port(args.port, args.baud)
    log = open(args.log, "a") if args.log else None

    def emit(text):
        sys.stdout.write(text)
        sys.stdout.flush()
        if log:
            log.write(text)
            log.flush()

    if args.listen is not None:
        emit(show(drain(port, quiet=args.listen, limit=args.listen)))
        return

    cmds = list(args.cmds)
    if args.file:
        with open(args.file) as fh:
            cmds += [ln.strip() for ln in fh if ln.strip() and not ln.startswith("#")]

    for cmd in cmds:
        emit(f"\n>>> {cmd}\n")
        emit(show(send(port, cmd, args.quiet, args.limit)))
        time.sleep(args.delay)


if __name__ == "__main__":
    main()
