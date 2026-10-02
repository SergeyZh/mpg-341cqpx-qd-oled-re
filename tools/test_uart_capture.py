#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import io
import json
import math
import signal
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import uart_capture


class Clock:
    def __init__(self, step: float = 0.01):
        self.value = -step
        self.step = step

    def __call__(self) -> float:
        self.value += self.step
        return self.value


class FakeSerial:
    port = "/dev/fake-explicit"
    baudrate = 115200

    def __init__(self, reads):
        self.reads = iter(reads)
        self.read_calls = 0
        self.write_calls = 0
        self.reset_calls = 0

    def read(self, count):
        self.read_calls += 1
        item = next(self.reads, b"")
        if isinstance(item, BaseException):
            raise item
        return item

    def write(self, data):
        self.write_calls += 1
        raise AssertionError("capture must never transmit")

    def reset_input_buffer(self):
        self.reset_calls += 1
        raise AssertionError("capture must not discard input")


class UartCaptureTests(unittest.TestCase):
    def paths(self, root: Path):
        return root / "capture.bin", root / "chunks.jsonl", root / "metadata.json"

    def test_preserves_raw_cr_nul_and_records_chunks_without_tx(self):
        with tempfile.TemporaryDirectory(prefix="uart-capture-") as temporary:
            root = Path(temporary)
            raw, chunks, metadata = self.paths(root)
            source = [b"BOOT 0x64729E3E\r\n", b"FAULT\x00X\r", b""]
            serial = FakeSerial(source)
            screen = io.StringIO()
            result = uart_capture.capture(serial, 0.12, raw, chunks, metadata,
                                          clock=Clock(), stdout=screen)
            expected = b"".join(source)
            self.assertEqual(raw.read_bytes(), expected)
            self.assertEqual(result["sha256"], hashlib.sha256(expected).hexdigest())
            self.assertEqual(result["bytes"], len(expected))
            self.assertEqual(result["chunks"], 2)
            rows = [json.loads(line) for line in chunks.read_text().splitlines()]
            self.assertEqual([(r["byte_offset"], r["length"]) for r in rows],
                             [(0, 17), (17, 8)])
            self.assertIn("FAULT\\x00X\r", screen.getvalue())
            self.assertEqual(json.loads(metadata.read_text()), result)
            self.assertEqual((serial.write_calls, serial.reset_calls), (0, 0))

    def test_restore_sigint_overrides_inherited_ignore(self):
        previous = signal.signal(signal.SIGINT, signal.SIG_IGN)
        try:
            uart_capture.restore_sigint()
            self.assertIs(signal.getsignal(signal.SIGINT), signal.default_int_handler)
        finally:
            signal.signal(signal.SIGINT, previous)

    def test_silent_timeout_is_complete_empty_evidence(self):
        with tempfile.TemporaryDirectory(prefix="uart-silent-") as temporary:
            root = Path(temporary)
            raw, chunks, metadata = self.paths(root)
            serial = FakeSerial([])
            result = uart_capture.capture(serial, 0.05, raw, chunks, metadata,
                                          clock=Clock(), stdout=io.StringIO())
            self.assertTrue(result["complete"])
            self.assertEqual(result["bytes"], 0)
            self.assertEqual(raw.read_bytes(), b"")
            self.assertEqual(chunks.read_bytes(), b"")
            self.assertEqual(result["sha256"], hashlib.sha256(b"").hexdigest())
            self.assertGreater(serial.read_calls, 0)

    def test_read_exception_keeps_partial_evidence_and_reports_error(self):
        with tempfile.TemporaryDirectory(prefix="uart-error-") as temporary:
            root = Path(temporary)
            raw, chunks, metadata = self.paths(root)
            serial = FakeSerial([b"STAGE 0x1\r\n", OSError("cable lost"), b"ignored"])
            result = uart_capture.capture(serial, 10, raw, chunks, metadata,
                                          clock=Clock(), stdout=io.StringIO())
            self.assertFalse(result["complete"])
            self.assertEqual(raw.read_bytes(), b"STAGE 0x1\r\n")
            self.assertEqual(result["errors"], ["OSError: cable lost"])
            self.assertEqual(len(chunks.read_text().splitlines()), 1)
            self.assertEqual(json.loads(metadata.read_text())["bytes"], 11)
            self.assertEqual((serial.write_calls, serial.reset_calls), (0, 0))

    def test_rejects_overwrite_before_reading(self):
        with tempfile.TemporaryDirectory(prefix="uart-existing-") as temporary:
            root = Path(temporary)
            raw, chunks, metadata = self.paths(root)
            chunks.write_text("keep")
            serial = FakeSerial([b"must not read"])
            with self.assertRaisesRegex(ValueError, "must not exist"):
                uart_capture.capture(serial, 1, raw, chunks, metadata,
                                     clock=Clock(), stdout=io.StringIO())
            self.assertEqual(serial.read_calls, 0)
            self.assertEqual(chunks.read_text(), "keep")
            self.assertFalse(raw.exists())
            self.assertFalse(metadata.exists())

    def test_nonfinite_bounds_and_cli_preflight_do_not_open_serial(self):
        with tempfile.TemporaryDirectory(prefix="uart-options-") as temporary:
            root = Path(temporary)
            raw, chunks, metadata = self.paths(root)
            serial = FakeSerial([])
            for seconds in (math.nan, math.inf, -math.inf, 0, -1, True):
                with self.subTest(seconds=seconds), self.assertRaisesRegex(
                        ValueError, "finite and positive"):
                    uart_capture.capture(serial, seconds, raw, chunks, metadata,
                                         clock=Clock(), stdout=io.StringIO())
            self.assertEqual(serial.read_calls, 0)

            chunks.write_text("existing")
            args = type("Args", (), dict(port="/dev/must-not-open", seconds=1,
                        raw=raw, chunks=chunks, metadata=metadata))()
            class SerialModule:
                @staticmethod
                def Serial(**kwargs):
                    raise AssertionError("serial opened before output preflight")
            with self.assertRaisesRegex(ValueError, "must not exist"):
                uart_capture.run(args, SerialModule)

    def test_interrupt_preserves_partial_evidence(self):
        with tempfile.TemporaryDirectory(prefix="uart-interrupt-") as temporary:
            root = Path(temporary)
            raw, chunks, metadata = self.paths(root)
            serial = FakeSerial([b"BOOT\r\n", KeyboardInterrupt()])
            result = uart_capture.capture(serial, 10, raw, chunks, metadata,
                                          clock=Clock(), stdout=io.StringIO())
            self.assertFalse(result["complete"])
            self.assertEqual(result["errors"], ["KeyboardInterrupt: interrupted"])
            self.assertEqual(raw.read_bytes(), b"BOOT\r\n")

    def test_serial_is_configured_closed_with_modem_controls_low(self):
        class Port:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.is_open = False
                self.dtr = None
                self.rts = None
                self.port = None

            def open(self):
                self.open_snapshot = (self.port, self.dtr, self.rts)
                self.is_open = True

        class SerialModule:
            @staticmethod
            def Serial(**kwargs):
                SerialModule.instance = Port(**kwargs)
                return SerialModule.instance

        port = uart_capture.open_serial_rx(SerialModule, "/dev/explicit")
        self.assertEqual(port.kwargs, dict(port=None, baudrate=115200, timeout=0.1,
                                          rtscts=False, xonxoff=False, dsrdtr=False))
        self.assertEqual(port.open_snapshot, ("/dev/explicit", False, False))
        self.assertTrue(port.is_open)


if __name__ == "__main__":
    unittest.main()
