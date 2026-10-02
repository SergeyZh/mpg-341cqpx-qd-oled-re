#!/usr/bin/env python3
"""Bounded RX-only UART capture with raw bytes and timestamped chunk evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import sys
import time


def _exists(path: Path) -> bool:
    return os.path.lexists(os.fspath(path))


def _stdout_text(data: bytes) -> str:
    out = []
    for byte in data:
        if byte in (9, 10, 13) or 0x20 <= byte <= 0x7E:
            out.append(chr(byte))
        else:
            out.append(f"\\x{byte:02x}")
    return "".join(out)


def validate_options(seconds: float, raw_path: Path, chunks_path: Path,
                     metadata_path: Path) -> None:
    if (not isinstance(seconds, (int, float)) or isinstance(seconds, bool) or
            not math.isfinite(seconds) or seconds <= 0):
        raise ValueError("seconds must be finite and positive")
    outputs = (raw_path, chunks_path, metadata_path)
    if len({os.path.abspath(path) for path in outputs}) != 3:
        raise ValueError("raw, chunks and metadata paths must be distinct")
    if any(_exists(path) for path in outputs):
        raise ValueError("output paths must not exist")
    if any(not path.parent.is_dir() for path in outputs):
        raise ValueError("every output parent must exist")


def capture(port, seconds: float, raw_path: Path, chunks_path: Path,
            metadata_path: Path, *, clock=time.monotonic, stdout=sys.stdout) -> dict:
    """Read until the monotonic deadline; preserve partial evidence on read errors."""
    validate_options(seconds, raw_path, chunks_path, metadata_path)

    started = clock()
    digest = hashlib.sha256()
    total = 0
    chunks = 0
    errors: list[str] = []
    with raw_path.open("xb") as raw, chunks_path.open("x", encoding="utf-8") as log:
        while clock() - started < seconds:
            try:
                data = port.read(4096)
            except KeyboardInterrupt:
                errors.append("KeyboardInterrupt: interrupted")
                break
            except Exception as error:  # Preserve evidence; CLI reports failure afterwards.
                errors.append(f"{type(error).__name__}: {error}")
                break
            if not data:
                continue
            if not isinstance(data, bytes):
                errors.append(f"invalid read result type: {type(data).__name__}")
                break
            offset = total
            now = clock()
            raw.write(data)
            raw.flush()
            os.fsync(raw.fileno())
            log.write(json.dumps({
                "monotonic_offset_ns": max(0, int((now - started) * 1_000_000_000)),
                "byte_offset": offset,
                "length": len(data),
            }, sort_keys=True) + "\n")
            log.flush()
            os.fsync(log.fileno())
            digest.update(data)
            total += len(data)
            chunks += 1
            stdout.write(_stdout_text(data))
            stdout.flush()
    elapsed = max(0.0, clock() - started)
    result = {
        "format": "raw-uart-capture-v1",
        "port": getattr(port, "port", None),
        "baud": getattr(port, "baudrate", 115200),
        "requested_seconds": seconds,
        "elapsed_seconds": elapsed,
        "bytes": total,
        "chunks": chunks,
        "sha256": digest.hexdigest(),
        "errors": errors,
        "complete": not errors,
        "tx_payload_bytes": 0,
        "modem_control_note": "DTR/RTS requested low before open; driver-level open glitches cannot be excluded",
        "raw_file": raw_path.name,
        "chunks_file": chunks_path.name,
    }
    with metadata_path.open("x", encoding="utf-8") as metadata:
        json.dump(result, metadata, indent=2, sort_keys=True)
        metadata.write("\n")
        metadata.flush()
        os.fsync(metadata.fileno())
    return result


def restore_sigint() -> None:
    """Make SIGINT raise KeyboardInterrupt even if the parent ignored it.

    A background job (`nohup ... &`) of a non-interactive shell starts with SIGINT
    ignored, and Python then installs no handler, so `kill -INT` was a no-op.
    """
    signal.signal(signal.SIGINT, signal.default_int_handler)


def open_serial_rx(serial_module, device: str):
    """Configure a closed port, request modem controls low, then open it."""
    port = serial_module.Serial(port=None, baudrate=115200, timeout=0.1,
                                rtscts=False, xonxoff=False, dsrdtr=False)
    port.dtr = False
    port.rts = False
    port.port = device
    port.open()
    return port


def run(args, serial_module) -> dict:
    # This must precede construction/open of a serial object.
    validate_options(args.seconds, args.raw, args.chunks, args.metadata)
    port = open_serial_rx(serial_module, args.port)
    try:
        return capture(port, args.seconds, args.raw, args.chunks, args.metadata)
    finally:
        port.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="explicit serial device; never auto-detected")
    parser.add_argument("--seconds", required=True, type=float)
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--chunks", required=True, type=Path)
    parser.add_argument("--metadata", required=True, type=Path)
    args = parser.parse_args()
    restore_sigint()
    try:
        import serial
        result = run(args, serial)
    except (OSError, ValueError) as error:
        parser.exit(2, f"UART capture refused: {error}\n")
    return 0 if result["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
