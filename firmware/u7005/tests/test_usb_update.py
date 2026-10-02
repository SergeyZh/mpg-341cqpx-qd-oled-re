"""USB host against the captured read protocol and an independent LDROM model.

The model follows Ghidra A0/00/AF and simulates successful FMC word writes.
It is not execution of the physical LDROM binary or a hardware erase test.
"""
import ctypes as C
import json
from pathlib import Path
import struct
import sys
import pytest
from conftest import PROJECT
from test_boot_metadata import bootlib, READ, WRITE  # pytest fixture + C boot policy

ROOT = PROJECT.parents[1]
sys.path.insert(0, str(ROOT/'tools'))
sys.path.insert(0, str(PROJECT/'tools'))
from package import package
import u7005_usb_image as images
from u7005_isp import APP, ISP, Loader
from u7005_usb_update import FirmwareLoader, WakeStalledApp, install, verify_installed


@pytest.fixture
def bundle(tmp_path):
    code = bytearray((i*13) & 255 for i in range(256))
    struct.pack_into('<II', code, 0, 0x20005000, 209)
    struct.pack_into('<4sIII', code, 192, b'U7BI', 1, len(code), 1)
    segments, manifest = package(bytes(code))
    build = tmp_path/'build'
    build.mkdir()
    (build/'u7005-code.bin').write_bytes(code)
    (build/'u7005-disk.bin').write_bytes(segments[1][1])
    (build/'u7005-manifest.json').write_text(json.dumps(manifest))
    backup = bytearray((i*7+19) & 255 for i in range(0x20000))
    backup[0x1e800] = 0
    struct.pack_into('<II', backup, images.USB_LENGTH, 0xdc00, sum(backup[:0xdc00]) & 65535)
    (tmp_path/'backup.bin').write_bytes(backup)
    (tmp_path/'config.bin').write_bytes(struct.pack('<III', *images.CONFIG))
    image, meta = images.prepare(build, tmp_path/'backup.bin', tmp_path/'config.bin')
    return image, meta, bytes(backup), build


class Trace:
    def event(self, **kw):
        pass


class LoaderDevice:
    def __init__(self, backup):
        self.flash = bytearray(backup)
        self.sequence, self.offset, self.total = 1, 0, 0
        self.pending, self.calls, self.timeouts = b'', [], []
        self.bad_config = False
        self.bad_sequence = self.bad_checksum = self.bad_final_sum = False
        self.drop_block = None
        self.block_count = 0
        self.app_running = False
        self.boot_callback = lambda: None
        self.closed = False

    def write(self, wire):
        assert len(wire) == 65 and wire[0] == 0
        request = bytearray(wire[1:])
        op, seq = struct.unpack_from('<II', request)
        self.calls.append(op)
        reply = bytearray(64)
        if op == 0xae:
            self.sequence = 1
        elif op == 0xa4:
            self.sequence = struct.unpack_from('<I', request, 8)[0]
        elif op == 0xa6:
            reply[8] = 0x15
        elif op == 0xb1:
            struct.pack_into('<I', reply, 8, 0x01205206)
        elif op == 0xa2:
            struct.pack_into('<II', reply, 8, images.CONFIG[0], 0x10000 if self.bad_config else images.DFBA)
        elif op == 0xca:
            struct.pack_into('<I', reply, 8, 2)
        elif op in (0xa0, 0):
            if op == 0xa0:
                start, self.total = struct.unpack_from('<II', request, 8)
                assert start == 0 and 0 < self.total <= images.USB_LENGTH and self.total % 4 == 0
                self.flash[:images.DFBA] = b'\xff' * images.DFBA
                self.offset = 0
            self.block_count += 1
            pos = 16 if op == 0xa0 else 8
            count = min(64-pos, self.total-self.offset)
            self.flash[self.offset:self.offset+count] = request[pos:pos+count]
            # Ghidra reads flash back into the request before summing the ACK.
            request[pos:pos+count] = self.flash[self.offset:self.offset+count]
            self.offset += count
            if self.offset == self.total:
                checksum = sum(self.flash[:self.total]) & 65535
                struct.pack_into('<II', self.flash, images.USB_LENGTH, self.total, checksum)
                # High bytes of the final result are stale CONFIG, not a uint32 sum.
                struct.pack_into('<H', reply, 8, checksum ^ int(self.bad_final_sum))
                reply[10:12] = b'\xff\xff'
        elif op == 0xaf:
            length, checksum = struct.unpack_from('<II', self.flash, images.USB_LENGTH)
            if length <= len(self.flash) and (sum(self.flash[:length]) & 65535) == checksum:
                self.boot_callback()
                self.app_running = True
            self.pending = b''
            return 65
        elif op != 0xab:
            raise AssertionError(f'forbidden command {op:x}')
        assert seq == self.sequence
        struct.pack_into('<H', reply, 0, (sum(request) & 65535) ^ int(self.bad_checksum))
        struct.pack_into('<I', reply, 4, self.sequence + (3 if self.bad_sequence else 1))
        self.sequence += 2
        self.pending = b'' if op in (0xa0, 0) and self.block_count == self.drop_block else bytes(reply)
        return 65

    def read(self, length, timeout_ms):
        assert length == 64
        self.timeouts.append(timeout_ms)
        reply, self.pending = self.pending, b''
        return reply

    def close(self):
        self.closed = True


def test_bundle_preserves_tail_and_excludes_dataflash(bundle, tmp_path):
    image, manifest, backup, _ = bundle
    assert len(image) == 0x1f7f8
    assert image[0x15800:] == backup[0x15800:0x1f7f8]
    assert manifest['backup']['dataflash_sha256'] == images.sha(backup[0x1f800:])
    dest = tmp_path/'install.bin'
    images.write(dest, image, manifest)
    assert images.load(dest) == (image, manifest)
    with pytest.raises(ValueError):
        images.write(dest, image, manifest)


@pytest.mark.parametrize('where', [0, 192, 200, 1000, 0x10000, 0x1e800, 0x1f7f7])
def test_corrupted_bundle_rejected_before_opening_usb(bundle, tmp_path, where):
    image, manifest, _, _ = bundle
    corrupt = bytearray(image)
    corrupt[where] ^= 1
    def never_open(*a, **kw):
        pytest.fail('USB must not open')
    with pytest.raises(ValueError):
        install(bytes(corrupt), manifest, tmp_path/'trace', opener=never_open)
    assert not (tmp_path/'trace').exists()


def test_old_code_without_descriptor_rejected_even_with_new_hashes(bundle):
    image, manifest, _, _ = bundle
    corrupt = bytearray(image)
    corrupt[192:196] = b'OLD!'
    manifest = {**manifest, 'sha256': images.sha(corrupt), 'sum16': sum(corrupt) & 65535}
    with pytest.raises(ValueError, match='U7BI'):
        images.validate(corrupt, manifest)


def test_complete_2304_packet_transfer_and_af(bundle):
    image, manifest, backup, _ = bundle
    dev = LoaderDevice(backup)
    loader = FirmwareLoader(dev, Trace())
    loader.inspect()
    loader.program(image, manifest)
    assert loader.verified and dev.block_count == 2304
    assert dev.flash[:images.USB_LENGTH] == image
    assert dev.flash[images.DFBA:] == backup[images.DFBA:]
    assert struct.unpack_from('<II', dev.flash, images.USB_LENGTH) == (len(image), manifest['sum16'])
    assert 30000 in dev.timeouts
    assert dev.calls.count(0xa0) == 1 and dev.calls.count(0) == 2303
    loader.boot()
    assert dev.calls[-1] == 0xaf
    assert not set(dev.calls) & {0xa1, 0xa3, 0xc3, 0xff, 0xab}


@pytest.mark.parametrize('block', [1, 2, 50, 2304])
def test_lost_ack_never_retries_or_boots(bundle, block):
    image, manifest, backup, _ = bundle
    dev = LoaderDevice(backup)
    loader = FirmwareLoader(dev, Trace())
    loader.inspect()
    dev.drop_block = block
    with pytest.raises(IOError):
        loader.program(image, manifest)
    before = len(dev.calls)
    with pytest.raises(RuntimeError):
        loader.boot()
    with pytest.raises(RuntimeError):
        loader.program(image, manifest)
    assert len(dev.calls) == before and dev.block_count == block


@pytest.mark.parametrize('fault', ['bad_checksum', 'bad_sequence', 'bad_final_sum'])
def test_protocol_fault_aborts(bundle, fault):
    image, manifest, backup, _ = bundle
    dev = LoaderDevice(backup)
    loader = FirmwareLoader(dev, Trace())
    loader.inspect()
    setattr(dev, fault, True)
    with pytest.raises(IOError):
        loader.program(image, manifest)
    assert loader.failed and not loader.verified
    assert not set(dev.calls) & {0xaf, 0xab, 0xff}


def test_wrong_dfba_cannot_start_erase(bundle):
    image, manifest, backup, _ = bundle
    dev = LoaderDevice(backup)
    dev.bad_config = True
    loader = FirmwareLoader(dev, Trace())
    with pytest.raises(RuntimeError):
        loader.inspect()
    with pytest.raises(RuntimeError):
        loader.program(image, manifest)
    assert dev.flash == backup and 0xa0 not in dev.calls


def test_read_only_loader_still_rejects_write_commands(bundle):
    _, _, backup, _ = bundle
    dev = LoaderDevice(backup)
    loader = Loader(dev, Trace())
    for opcode in (0xa0, 0, 0xa1, 0xa3, 0xc3, 0xff, 0xaf):
        with pytest.raises(ValueError):
            loader.command(opcode)
    assert not dev.calls


def test_read_protocol_matches_physical_capture():
    events = [json.loads(line) for line in
              (PROJECT/'tests/data/ldrom-probe-2026-09-13.jsonl').read_text().splitlines()]
    events = iter(events)
    class Replay:
        def write(self, packet):
            event = next(events)
            assert event['direction'] == 'out' and packet == b'\0'+bytes.fromhex(event['packet'])
            return len(packet)
        def read(self, n, timeout_ms):
            event = next(events)
            assert event['direction'] == 'in'
            return bytes.fromhex(event['packet'])
    loader = Loader(Replay(), Trace())
    loader.inspect()
    loader.command(0xab, reset=True)
    assert next(events, None) is None


class World:
    def __init__(self, backup, bootlib):
        self.loader = LoaderDevice(backup)
        self.loader.app_running = True
        self.opened = []
        self.bootlib = bootlib
        self.loader.boot_callback = self.normalize

    def normalize(self):
        def read(address, value):
            value[0] = struct.unpack_from('<I', self.loader.flash, address)[0]
            return True
        def write(words):
            struct.pack_into('<II', self.loader.flash, images.USB_LENGTH, words[0], words[1])
            return True
        length = struct.unpack_from('<I', self.loader.flash, 200)[0]
        assert self.bootlib.boot_metadata_prepare(length, READ(read), WRITE(write))

    def open(self, ids, timeout=10):
        self.opened.append(ids)
        if ids == ISP:
            return self.loader
        if not self.loader.app_running:
            raise TimeoutError('application unavailable')
        world = self
        class App:
            pending = b''
            def write(self, packet):
                op = packet[1]
                reply = bytearray(64)
                reply[:2] = b'\x01\x5a'
                if op == 0xa0:
                    world.loader.app_running = False
                elif op == 0xb0:
                    reply[2], reply[4] = 0x54, 0x15
                    struct.pack_into('>II', reply, 5, 0xd926,
                                     struct.unpack_from('<I', world.loader.flash, images.USB_LENGTH+4)[0])
                elif op == 0xb2:
                    struct.pack_into('>I', reply, 2, 0x01205206)
                elif op == 0xb4:
                    reply[2:6] = world.loader.flash[0x1f800:0x1f804]
                elif op == 0xd2:
                    reply[1:12] = b'\xd0b00000000\r'
                    reply[10] = 48 + world.loader.flash[0x1e800]
                elif op == 0xe2:
                    reply[2:12] = b'U7EX\x01\x4a\x01\x00\x02\x34'
                else:
                    raise AssertionError(f'app opcode {op:x}')
                self.pending = bytes(reply)
                return len(packet)
            def read(self, n, timeout_ms):
                return self.pending
            def close(self):
                pass
        return App()


def test_full_install_runs_actual_c_normalization_and_checks_app(bundle, bootlib, tmp_path):
    image, manifest, backup, _ = bundle
    world = World(backup, bootlib)
    result = install(image, manifest, tmp_path/'trace', opener=world.open)
    assert result['complete'] and result['transfer_verified'] and not result['independent_readback']
    assert world.opened == [APP, ISP, APP]
    assert world.loader.flash[images.DFBA:] == backup[images.DFBA:]
    assert struct.unpack_from('<II', world.loader.flash, images.USB_LENGTH) == (256, manifest['code']['sum16'])
    assert json.loads((tmp_path/'trace/result.json').read_text())['complete']
    assert (tmp_path/'trace/image.bin').read_bytes() == image


def test_already_isp_stay_then_run(bundle, bootlib, tmp_path):
    image, manifest, backup, _ = bundle
    world = World(backup, bootlib)
    result = install(image, manifest, tmp_path/'write', already_isp=True, stay_in_isp=True, opener=world.open)
    assert not result['complete'] and result['transfer_verified']
    assert world.opened == [ISP] and 0xaf not in world.loader.calls
    result = install(image, manifest, tmp_path/'run', run_only=True, opener=world.open)
    assert result['complete'] and world.loader.calls.count(0xa0) == 1


def test_failed_install_keeps_log_and_never_starts_app(bundle, bootlib, tmp_path):
    image, manifest, backup, _ = bundle
    world = World(backup, bootlib)
    world.loader.drop_block = 3
    with pytest.raises(IOError):
        install(image, manifest, tmp_path/'trace', already_isp=True, opener=world.open)
    result = json.loads((tmp_path/'trace/result.json').read_text())
    assert not result['complete'] and not result['transfer_verified'] and result['error']
    assert world.opened == [ISP] and 0xaf not in world.loader.calls and world.loader.closed


def test_wrong_board_rejected_before_entering_isp(bundle, bootlib, tmp_path):
    image, manifest, backup, _ = bundle
    world = World(backup, bootlib)
    world.loader.flash[images.DFBA] ^= 1
    with pytest.raises(RuntimeError, match='board ID'):
        install(image, manifest, tmp_path/'trace', opener=world.open)
    assert world.opened == [APP] and not world.loader.calls


class SleepingApp:
    """IN remains queued until GET_REPORT produces another USB interrupt."""
    def __init__(self, app):
        self.app = app
        self.awake = False
        self.wakes = 0
        self.commands = []

    def write(self, packet):
        self.awake = False
        self.commands.append(packet[1])
        return self.app.write(packet)

    def read(self, n, timeout_ms):
        return self.app.read(n, timeout_ms) if self.awake else b''

    def get_input_report(self, report_id, n):
        assert report_id == 1 and n == 64
        self.wakes += 1
        self.awake = True
        # A valid-looking stale report must never be accepted as the reply.
        return b'\x01\x5a'+bytes(62)

    def close(self):
        self.app.close()


@pytest.mark.parametrize('broken_after', [False, True])
def test_wakeup_only_before_flash_never_masks_broken_new_firmware(bundle, bootlib, tmp_path, broken_after):
    image, manifest, backup, _ = bundle
    world = World(backup, bootlib)
    apps = []
    def open_device(ids, timeout=10):
        dev = world.open(ids, timeout)
        if ids == APP:
            if not apps or broken_after:
                dev = SleepingApp(dev)
            apps.append(dev)
        return dev
    if broken_after:
        with pytest.raises(TimeoutError):
            install(image, manifest, tmp_path/'trace', wake_stalled_app=True, opener=open_device)
        result = json.loads((tmp_path/'trace/result.json').read_text())
        assert not result['complete'] and result['transfer_verified']
        assert result['stage'] == 'verifying_app' and apps[1].wakes == 0
    else:
        assert install(image, manifest, tmp_path/'trace', wake_stalled_app=True, opener=open_device)['complete']
    assert apps[0].commands == [0xb0, 0xb2, 0xb4, 0xd2, 0xa0]
    assert apps[0].wakes == 4


def test_verify_wakes_but_never_writes_flash_or_enters_isp(bundle, bootlib, tmp_path):
    image, manifest, backup, _ = bundle
    world = World(backup, bootlib)
    struct.pack_into('<I', world.loader.flash, images.USB_LENGTH+4, manifest['code']['sum16'])
    app = SleepingApp(world.open(APP))
    result = verify_installed(image, manifest, tmp_path/'trace', wake_stalled_app=True,
                              opener=lambda ids: app)
    assert result['complete'] and result['read_only'] and result['wake_stalled_app']
    assert result['after']['metadata_code_sum_matches']
    assert not world.loader.calls and app.commands == [0xb0, 0xb2, 0xb4, 0xe2, 0xd2]
    assert app.wakes == 5


def test_wakeup_never_retries_command_or_returns_cached_report():
    class Dead:
        writes = wakes = 0
        def write(self, packet):
            self.writes += 1
            return len(packet)
        def read(self, n, timeout_ms):
            return b''
        def get_input_report(self, report_id, n):
            self.wakes += 1
            return b'\x01\x5a'+bytes(62)
    dev = Dead()
    wake = WakeStalledApp(dev, Trace())
    wake.write(b'\x01\xb0'+bytes(62))
    for _ in range(10):
        assert not wake.read(64, 300)
    assert dev.writes == dev.wakes == 1
    with pytest.raises(ValueError):
        wake.write(b'\x01\xb6'+bytes(62))
