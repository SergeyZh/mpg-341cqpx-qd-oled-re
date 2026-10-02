#!/usr/bin/env python3
"""Установочный USB BIN и запись приложения U7005 через штатный LDROM 0x15.

prepare/check работают без USB. flash стирает APROM [0,0x1F800), сохраняя
DataFlash/CONFIG/LDROM/SPROM. Ошибки останавливают сеанс без retry или запуска.
Это инструмент U7005, не прошивальщик SPI-флеша скалера U4002.
"""
import argparse
import json
from pathlib import Path
import struct
import sys

from u7005_isp import APP, ISP, Loader, Trace, app_command, app_info, open_device
from u7005_usb_image import USB_LENGTH, load, prepare, validate, write

ROOT = Path(__file__).resolve().parents[1]


class WakeStalledApp:
    """Обход выключенного SysTick в первой сборке, только по явному флагу.

    GET_REPORT будит MCU, но возвращает кеш: его данные никогда не считаются
    ответом команды. Ожидаем обычный interrupt IN, не повторяя SET_REPORT.
    """
    def __init__(self, dev, trace):
        self.dev, self.trace = dev, trace
        self.woken = False

    def write(self, packet):
        if len(packet) != 64 or packet[0] != 1 or packet[1] not in (0xb0, 0xb2, 0xb4, 0xd2, 0xe2, 0xa0):
            raise ValueError('обход разрешён только для сведений приложения и входа A0')
        self.woken = False
        return self.dev.write(packet)

    def read(self, length, timeout_ms):
        reply = self.dev.read(length, timeout_ms=timeout_ms)
        if not reply and not self.woken:
            self.woken = True
            self.trace.event(mode='app', direction='get_input_report', report_id=1, length=64)
            cached = bytes(self.dev.get_input_report(1, 64))
            self.trace.event(mode='app', direction='control_in', packet=cached.hex())
            reply = self.dev.read(length, timeout_ms=timeout_ms)
        return reply

    def close(self):
        self.dev.close()


class FirmwareLoader(Loader):
    """Только последовательная A0/00; запрещён повтор даже после потери ACK."""
    def __init__(self, dev, trace):
        super().__init__(dev, trace)
        self.inspected = self.started = self.verified = self.failed = False

    def inspect(self):
        self.inspected = False
        if self.started:
            raise RuntimeError('после начала записи нельзя повторять инициализацию сеанса')
        result = super().inspect()
        self.inspected = True
        return result

    def program(self, image, manifest, progress=lambda done, total: None):
        validate(image, manifest)
        if not self.inspected or self.started:
            raise RuntimeError('нужен новый проверенный сеанс LDROM')
        self.started = True
        try:
            offset = 0
            while offset < len(image):
                first = offset == 0
                count = min(48 if first else 56, len(image)-offset)
                data = image[offset:offset+count]
                if first:
                    data = struct.pack('<II', 0, len(image)) + data
                # A0 erases 63 pages before its first reply; do not resend on timeout.
                reply = self._exchange(0xA0 if first else 0, data,
                                       timeout_ms=30000 if first else 5000)
                offset += count
                if offset == len(image) and struct.unpack_from('<H', reply, 8)[0] != manifest['sum16']:
                    raise IOError('итоговая сумма прочитанного APROM не совпала с образом')
                progress(offset, len(image))
            self.verified = True
        except BaseException:
            self.failed = True
            raise

    def boot(self):
        if not self.inspected or self.failed or (self.started and not self.verified):
            raise RuntimeError('нельзя запускать приложение после неудачной записи')
        # AF validates metadata and checksum; unlike AB it cannot blindly boot APROM.
        self._exchange(0xAF, reset=True)


def app_query(dev, request, prefix, trace):
    packet = request.ljust(64, b'\0')
    trace.event(mode='app', direction='out', packet=packet.hex())
    if dev.write(packet) != 64:
        raise IOError('неполная запись HID приложения')
    for _ in range(12):
        reply = bytes(dev.read(64, timeout_ms=250))
        trace.event(mode='app', direction='in', packet=reply.hex())
        if len(reply) == 64 and reply.startswith(prefix):
            return reply
    raise TimeoutError(f'нет ответа приложения на {request.hex()}')


def app_mode(dev, trace):
    reply = app_query(dev, b'\x01\xd2', b'\x01\xd0b0000000', trace)
    return (reply[10] - ord('0')) & 255


def expected_mode(manifest):
    return 1 if manifest['usb_mode'] == 255 else manifest['usb_mode']


def verify_app(dev, manifest, trace):
    info = app_info(dev, trace)
    if (info['app_version'] != 0x54 or info['aprom_checksum'] != manifest['code']['sum16']
            or info['board_id'] != manifest['backup']['board_id']):
        raise IOError(f'приложение/метаданные/board ID не совпали с комплектом: {info}')
    reply = app_query(dev, b'\x01\xe2', b'\x01\x5aU7EX', trace)
    if reply[6:12] != b'\x01\x4a\x01\x00\x02\x34':
        raise IOError('не совпала версия расширения U7EX')
    mode = app_mode(dev, trace)
    if mode != expected_mode(manifest):
        raise IOError('USB-режим после установки не совпал с сохранённым')
    return {**info, 'usb_mode': mode, 'extension': 'U7EX v1',
            'metadata_code_sum_matches': True}


def plan(manifest):
    return {'image_sha256': manifest['sha256'], 'bytes': manifest['length'],
            'packets': 1 + (manifest['length']-48+55)//56,
            'erase': '[0x00000,0x1F800), 63 pages',
            'write': '[0x00000,0x1F7F8), then LDROM length/checksum',
            'usb_sum16': f"{manifest['sum16']:04X}",
            'code_sum16_after_first_boot': f"{manifest['code']['sum16']:04X}",
            'usb_mode': manifest['usb_mode'], 'board_id': f"{manifest['backup']['board_id']:08X}",
            'preserved': ['DataFlash', 'CONFIG', 'LDROM', 'SPROM'],
            'hardware_tested': False}


def install(image, manifest, directory, *, already_isp=False, stay_in_isp=False,
            run_only=False, wake_stalled_app=False, opener=open_device):
    # All file validation and creation happen before opening a USB device.
    validate(image, manifest)
    trace = Trace(directory)
    result = {'complete': False, 'stage': 'preflight', 'image': manifest,
              'transfer_verified': False, 'independent_readback': False,
              'already_isp': already_isp, 'run_only': run_only,
              'wake_stalled_app_preflight': wake_stalled_app}

    def stage(name):
        result['stage'] = name
        trace.result(result)

    try:
        with (directory / 'image.bin').open('xb') as f:
            f.write(image)
        stage('preflight')
        if not already_isp and not run_only:
            dev = opener(APP)
            if wake_stalled_app:
                dev = WakeStalledApp(dev, trace)
            try:
                result['before'] = app_info(dev, trace)
                if result['before']['board_id'] != manifest['backup']['board_id']:
                    raise RuntimeError('board ID не совпал с резервной копией; запись отменена')
                if app_mode(dev, trace) != expected_mode(manifest):
                    raise RuntimeError('USB mode изменился с момента дампа; пересоберите комплект из свежего APROM')
                stage('entering_isp')
                app_command(dev, 0xA0, trace)
            finally:
                dev.close()
        stage('opening_isp')
        dev = opener(ISP, timeout=20)
        try:
            loader = FirmwareLoader(dev, trace)
            result['isp'] = loader.inspect()
            if not run_only:
                stage('writing_aprom')
                last_percent = -10

                def progress(done, total):
                    nonlocal last_percent
                    percent = done*100//total
                    if percent >= last_percent+10 or done == total:
                        print(f'APROM: {done}/{total} ({percent}%)', flush=True)
                        last_percent = percent

                loader.program(image, manifest, progress)
                result['transfer_verified'] = True
                stage('written_waiting_for_boot')
                if stay_in_isp:
                    return result
            stage('starting_app')
            loader.boot()
        finally:
            dev.close()
        stage('verifying_app')
        dev = opener(APP, timeout=30)
        try:
            result['after'] = verify_app(dev, manifest, trace)
        finally:
            dev.close()
        result['complete'] = True
        stage('complete')
        return result
    except BaseException as exc:
        result['error'] = f'{type(exc).__name__}: {exc}'
        # Closing HID is the only cleanup: never retry a block or boot on failure.
        raise
    finally:
        try:
            trace.result(result)
        finally:
            trace.file.close()


def verify_installed(image, manifest, directory, *, wake_stalled_app=False, opener=open_device):
    """Только сведения приложения: без ISP, сброса и записи flash."""
    validate(image, manifest)
    trace = Trace(directory)
    result = {'complete': False, 'read_only': True, 'image_sha256': manifest['sha256'],
              'wake_stalled_app': wake_stalled_app, 'independent_readback': False}
    try:
        dev = opener(APP)
        if wake_stalled_app:
            dev = WakeStalledApp(dev, trace)
        try:
            result['after'] = verify_app(dev, manifest, trace)
        finally:
            dev.close()
        result['complete'] = True
        return result
    except BaseException as exc:
        result['error'] = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        try:
            trace.result(result)
        finally:
            trace.file.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    pack = sub.add_parser('prepare', help='создать BIN + JSON из сборки и резервного APROM, без USB')
    pack.add_argument('--build', type=Path, default=ROOT / 'out/u7005')
    pack.add_argument('--backup', type=Path, required=True)
    pack.add_argument('--config', type=Path, required=True)
    pack.add_argument('-o', '--output', type=Path, required=True)
    check = sub.add_parser('check', help='проверить комплект и показать план, без USB')
    check.add_argument('image', type=Path)
    flash = sub.add_parser('flash', help='записать APROM и проверить запуск приложения')
    flash.add_argument('image', type=Path)
    flash.add_argument('--out', type=Path, required=True, help='новый каталог исходных USB-пакетов и результата')
    flash.add_argument('--already-isp', action='store_true', help='мост уже 0416:3F00; board ID до записи недоступен')
    flash.add_argument('--stay-in-isp', action='store_true', help='оставить в LDROM после записи для независимого SWD read-back')
    flash.add_argument('--wake-stalled-app', action='store_true',
                       help='обход выключенного SysTick первой сборки только ДО записи; новая проверяется без обхода')
    verify = sub.add_parser('verify', help='проверить уже работающее приложение, без записи и сброса')
    verify.add_argument('image', type=Path)
    verify.add_argument('--out', type=Path, required=True)
    verify.add_argument('--wake-stalled-app', action='store_true', help='проверять с обходом выключенного SysTick первой сборки')
    run = sub.add_parser('run', help='AF: проверить сумму и запустить ранее записанное приложение, без повторной передачи')
    run.add_argument('image', type=Path)
    run.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.action == 'prepare':
            image, manifest = prepare(args.build, args.backup, args.config)
            write(args.output, image, manifest)
            print(f'Созданы {args.output} и {args.output.with_suffix(".json")}')
        else:
            image, manifest = load(args.image)
            if args.action != 'verify':
                print(json.dumps(plan(manifest), ensure_ascii=False, indent=2), flush=True)
            if args.action in ('flash', 'run'):
                result = install(image, manifest, args.out,
                                 already_isp=getattr(args, 'already_isp', False),
                                 stay_in_isp=getattr(args, 'stay_in_isp', False),
                                 wake_stalled_app=getattr(args, 'wake_stalled_app', False),
                                 run_only=args.action == 'run')
                if result['complete']:
                    print('Приложение отвечает, U7EX и сумма кода подтверждены; полного read-back через USB нет.')
                else:
                    print('Передача проверена; приложение не запускалось. Для запуска используйте run.')
            elif args.action == 'verify':
                result = verify_installed(image, manifest, args.out, wake_stalled_app=args.wake_stalled_app)
                print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'Ошибка: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
