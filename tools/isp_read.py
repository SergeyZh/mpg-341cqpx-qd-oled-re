#!/usr/bin/env python3
"""Читает SPI-флеш, AHB и I2C-EEPROM U4003 с ПК через USB-мост U7005.

Повторяет тот доступ к флешу, которым пользуется штатная утилита обновления
(`docs/usb-isp-protocol.md`): HID-отчёты `0x04` на устройстве `1462:3fa4`
выкладываются в I²C, регистровое окно `0xA700` + опкод `0x25` на слейве `0x6E`
исполняет SPI-транзакцию. Здесь разрешены **только читающие** SPI-команды — белый
список ниже; ничего пишущего или стирающего тул не пошлёт. RX проверен живьём;
попытка длинного Page Program через это окно 2026-08-22 не прошла read-back.

Чтение flash автоматически использует быстрый 0x4A после E2/U7EX discovery.
Старому мосту 0x4A не отправляется: без расширения остаётся прежний SPI-путь.
--flash-read-method legacy принудительно оставляет его, 4a требует расширение.
--read задаёт смещение в текущем банке EAR; для сквозного адреса обоих банков
служит u7005_flash_read.py. Содержимое flash не меняется.

    tools/isp_read.py --jedec                     # прочитать JEDEC ID (проверка связи)
    tools/isp_read.py --jedec --bootloader        # продолжить вход из recovery bootloader
    tools/isp_read.py --read 0x0 0x100 -o out/head.bin
    tools/isp_read.py --ahb-read 0x9f0a0100 0x100 -o out/ahb.bin
    tools/isp_read.py --reg-read 0xf1d0 9
    tools/isp_read.py --reg-read 0xd511 1 --light  # на работающем мониторе
    tools/isp_read.py --heartbeat
    tools/isp_read.py --recover --reuse             # выйти из ISP без power-cycle
    tools/isp_read.py --eeprom-read 0x50 0x0 0x40 -o out/u4003-head.bin
    tools/isp_read.py --eeprom-read 0x58 0xc000 1  # CDA
    tools/isp_read.py --probe-buffer              # выяснить размер приёмного окна
    tools/isp_read.py --read 0x0 0x40 --dry-run   # показать кадры, ничего не слать

Базовый SPI/AHB путь проверен на живом мониторе 2026-08-16. Первый прогон после
изменений транспорта всё равно лучше делать с `--jedec`: он должен вернуть
`C8 40 19` (GigaDevice GD25Q256). Если вернулось другое или тул сообщил об ошибке
связи — остановиться и разобраться.

Запускать **на машине с подключённым монитором** (та, где ставили обновление).
Если устройства `1462:3fa4` в системе нет, тул сразу это скажет и не будет
слать команды в пустоту — на macOS `hid.open` для отсутствующего устройства
не падает, поэтому присутствие проверяется явно через `hid.enumerate`.

**Лёгкий вход `--light`** (`docs/nt68503-i2c-service-protocol.md`) обычную работу
монитора не останавливает: блок SETUP не проигрывается, ядра Leon2 не глушатся,
картинка и кнопки живут. Доступны только чтения регистров. **Консоль Leon2 Main на
контакте 7 при этом пропадает в обе стороны** — независимого свидетеля во время
сеанса нет (`docs/nt68503-i2c-service-protocol.md`). Окно около шести секунд,
дальше скалер сбрасывается сам — и один раз из трёх это оставило монитор в тупиковом
состоянии, поэтому тул закрывает сеанс сам кадром `34 06 3c`: монитор перезагружается
и возвращается в рабочее состояние. Вход из непроверенного состояния даёт тот же тупик,
поэтому базовая линия `58…` проверяется обязательно.

**Полный вход в ISP останавливает обычную работу монитора.** После чтения нужно либо
передёрнуть питание, либо выполнить `--recover`: завершённый дескриптор STBC FW.034
повторно пускается через `F1D0=0x87`. Для recovery загрузчика с пустым F1D и
Share Structure из нулей/FF при GD25Q256E, EAR=0 применяется watchdog `F0E0=55`.
Он заново запускает первичный загрузчик; проверки предшествуют сбросу.
Другие дескрипторы не принимаются автоматически. Flash и U4003 при этом не пишутся.
После recovery код выхода 2 означает: команда сброса отправлена, но проверка
USB/UART недоступна; это не доказательство неудачной загрузки. Если до ISP монитор
был Power Off, штатная прошивка может снова выключить его вместе с U7005.
Ответ `5800110` проверяет локальный USB-обработчик U7005 (Macro/Navi key),
а не UART/STBC/Main; при чтении сбрасывается защёлка события. Реальный выход
подтверждён перезапуском, кнопками и OSD 2026-08-22.

`enter()` проигрывает блок инициализации ISP **дословно из захвата обновления**
(константа SETUP, 30 команд в том же порядке): a0, разблокировка, init слейва
0xB0, настройка регистров. Раньше тул бил по SPI-контроллеру сразу после входа
и, по-видимому, ронял скалер (перезагрузка в начале сеанса). Команду `a1`
(commit → перезагрузка в конце обновления) тул не шлёт вовсе, поэтому в конце
монитор сам не перезагружается. Для выхода из оставленного ISP-состояния нужен
`--recover --reuse`; полный цикл проверен живьём 2026-08-22.

SPI-чтение адресуется 24 битами — оно достаёт только нижние 16 МиБ флеша (слот 0).
Верхний банк требует команды расширенного адреса `0xC5`, а это запись в регистр
микросхемы; тул её не делает. Это ограничение не относится к `--ahb-read`, где адрес
32-битный.

`--ahb-read` — отдельный **экспериментальный** путь чтения 32-битного адресного
пространства Leon2 через аппаратный мост PBus→AHB. Последовательность регистров
`0xCD80`…`0xCD8C` восстановлена из `FUN_CD27` внутреннего 8051.

Живая проверка 2026-08-16 подтвердила весь путь: исходное `CD8C=1`, после пуска ready
меняется `1→0→1`, а физический диапазон `0x9F0A0100` возвращает непустые данные общей
памяти, включая читаемые UART-кадры. Порядок байтов также подтверждён этим ASCII.

Но CPU-visible диапазон service runtime `0xA002F700…0xA002F7FF` вернул только нули; такими же
оказались `0xA802BB00` и `0xA002D510`. Прямой service-read `F770…F773` тоже дал нули,
тогда как контрольный service-регистр `D511` вернул `0x17`. Следовательно,
`0xA002F770` не доступен через найденное отображение PBus→AHB либо имеет другой
физический alias; нулевой результат **не считать дампом этой памяти**. Через консоль
`MDBG mem 0xA002F770` код читается: вывод меняет порядок байтов внутри каждого
32-битного слова. В FW.034 функция отправки mailbox находится по `0xA002F3EC`, а
`0xA002F770` является её адресом только в FW.037. Запрос CPU-visible
адреса `0x001516E8` не завершился и оставил bridge busy.

Чтение MMIO может иметь побочные эффекты; произвольные адреса не перебирать. После
timeout обязательно передёрнуть питание, не пытаться программно сбрасывать `CD8C`
неизвестным значением.

`--eeprom-read` использует этот же путь, чтобы битовым дёрганием GPIO банка 4
прочитать U4003. USB-I2C U7005 физически подключён к service/DDC-порту, а не к шине
EEPROM, поэтому простой заменой slave-адреса `0x6E` на `0x50` до неё не добраться.
Инструмент меняет только AHB/GPIO-регистры, необходимые I2C-master; U4003 получает
строго random-read: адрес записи, два байта смещения, RESTART, адрес чтения и чтение.
Байтов данных в write-фазе нет, EEPROM write cycle невозможен. Разрешены только
массив `0x50` (`0x0000..0x7fff`), ID page `0x58` (`0x0000..0x003f`) и CDA
`0x58:0xc000` (один байт). Общего примитива EEPROM-write здесь намеренно нет.

Перед первым MMIO-write инструмент проверяет AHB-write на последнем data-слове
неактивного I2C-slot 3 в общем portal 0: сохраняет слово, пишет контрольное значение,
проверяет и восстанавливает оригинал. Status-слово slot не меняется, поэтому событие
для Main не публикуется. До успешной проверки GPIO не трогаются. После операции
исходные DATA/DIR банка 4 восстанавливаются даже при ошибке. Проверка 2026-08-22
подтвердила оба адреса на живом мониторе: CDA
`0x58:0xc000` вернул `00`, а `0x50:0` — первые восемь байт
`21 48 11 0b b0 00 00 00`, совпавшие с дампом Raspberry Pi.
Из-за большого числа USB round-trip это путь для коротких проб, не для быстрого
полного дампа 32 КБ.

Зависимость: `hidapi` (`pip install hidapi` — пакет `hidapi`, модуль `hid`).
"""

import argparse
import sys
import time

from u7005_flash_read import FlashReader, UnsupportedExtensionError


def add_flash_read_argument(parser):
    parser.add_argument('--flash-read-method', choices=('auto', 'legacy', '4a'),
                        default='auto', help='чтение flash: auto — 0x4A после E2/U7EX, '
                        'иначе старый SPI; legacy — только старый SPI; '
                        '4a — требовать новое расширение моста')


def validate_flash_read_range(addr, length, chunk=249):
    if not 0 <= addr < 0x1000000 or length < 0 or addr + length > 0x1000000:
        raise ValueError('диапазон чтения должен лежать внутри текущего 16-МиБ '
                         'банка EAR; для сквозного адреса используйте u7005_flash_read.py')
    if chunk <= 0:
        raise ValueError('размер порции чтения должен быть положительным')

VID, PID = 0x1462, 0x3FA4

# Адреса I²C-слейвов внутри отчёта 0x04 (семёрочные, сдвинутые влево).
RD, WR = 0x6F, 0x6E              # слейв скалера: чтение / запись
OP_WRITE_REG = 0x78             # записать регистр по 16-битному адресу
OP_READ_REG = 0x87              # прочитать регистр
OP_SPI_RUN = 0x25               # запустить подготовленную SPI-транзакцию

# Кадры сеанса на специальный write address 0x04 (docs/mcu-u7005.md, § a0/a1).
# Третий байт — селектор действия: 0x36 открыть, 0x3c commit с перезагрузкой.
SESSION_OPEN = bytes([0x04, 0xA0, 0x6F, 0x00, 0x04, 0x34, 0x06, 0x36])
SESSION_COMMIT = bytes([0x04, 0xA0, 0x6F, 0x00, 0x04, 0x34, 0x06, 0x3C])

# Регистровое окно SPI-транзакции (docs/usb-isp-protocol.md).
F0C0, A700 = 0xF0C0, 0xA700

# PBus→AHB bridge внутреннего 8051 (FUN_CD27). Адрес и данные аппаратный блок
# принимает младшим байтом вперёд. CD8C.bit0 до запуска обязан быть 1 (idle/ready),
# запись CD8C=0x40 сбрасывает его, а завершение снова выставляет. Штатный код затем
# читает CD88..CD8B. Это подтверждается JNZ в исходных байтах FUN_CD27; декомпилятор
# развернул условие неверно.
AHB_ADDR = 0xCD80
AHB_WDATA = 0xCD84
AHB_DATA = 0xCD88
AHB_CTRL = 0xCD8C
AHB_START = 0x40
AHB_WRITE_START = 0x80
AHB_READY = 0x01
AHB_POLL_LIMIT = 20

LEON2_MAIN_CTRL = 0x9F020008
LEON2_SUB_CTRL = 0x9F120008
LEON2_STOP = 0x00001003
LEON2_RUN_SET = 0x00001000
LEON2_RUN_CLEAR = 0x00001003
LEON2_MAIN_TICK = 0x9F065BA4       # CPU A8029BA4, физический alias FW.034

# Дескриптор штатного STBC Main FW.034, оставшийся после ISP-входа. Пуск F1D0=87
# разрешён только при полном совпадении: это защита от запуска неизвестного окна.
STBC_WINDOW = 0xF1D0
STBC_FW034_DESCRIPTOR = bytes.fromhex('00 26 f0 00 00 01 26 f0 00')
REG_WATCHDOG_F0E0 = 0xF0E0
WATCHDOG_START_OR_RELOAD = 0x55
STBC_TIMER0_TICK = 0xA1E4

# Последнее (пятое) data-слово I2C-slot 3 общего portal 0. Событие публикуется
# ненулевым первым словом slot по +0x9C, которого probe не касается. Значение здесь
# всегда восстанавливается до любых MMIO-записей. +0xFC не подошёл: это не обычная
# RAM, запись в неописанную часть аппаратного portal игнорируется.
AHB_WRITE_PROBE = 0x9F0A01AC

# GPIO bank 4, программная I2C-шина U4003 (docs/nt68503-hardware.md §6.2).
EEPROM_GPIO_DATA = 0xCF03C00C
EEPROM_GPIO_DIR = 0xCF03C020
EEPROM_SCL = 1 << 0
EEPROM_SDA = 1 << 1
EEPROM_ADDRS = (0x50, 0x58)
EEPROM_CLOCK_POLL_LIMIT = 20

# Блок инициализации ISP-режима, снятый из захвата обновления дословно и в том же
# порядке (docs/usb-isp-protocol.md, «Фаза настройки»). Утилита проигрывает его между
# входом и первым чтением; без него запись в SPI-контроллер попадает по ещё не
# остановившемуся скалеру и роняет его. 'raw' — кадры на слейвы 0x04/0xB0 без
# длины-обрамления, шлём побайтово; 'wr'/'rd' — запись/чтение регистра скалера.
SETUP = [
    ('raw', bytes.fromhex('04a06f0004340636'), 0xA0),   # init слейва 0x04 → a5 00
    ('wr', 0xF0E0, 0xAA), ('wr', 0xF0E2, 0xAA),          # разблокировка SPI-контроллера
    ('rd', 0xF049, None), ('wr', 0xF055, 0x01),
    ('raw', bytes.fromhex('04bc0000b0ff3d'), 0xBC),      # init слейва 0xB0 (ISP)
    ('raw', bytes.fromhex('04be0000b0800800029f0010'), 0xBE),
    ('raw', bytes.fromhex('04bc0000b08c80'), 0xBC),
    ('raw', bytes.fromhex('04bc0000b0ff3d'), 0xBC),
    ('raw', bytes.fromhex('04be0000b0800800129f0010'), 0xBE),
    ('raw', bytes.fromhex('04bc0000b08c80'), 0xBC),
    ('wr', 0xF1DF, 0x80), ('wr', 0xF1A8, 0x02),
    ('wr', 0xF0E0, 0xAA), ('wr', 0xF0E2, 0xAA),
    ('wr', 0xF068, 0x9F), ('wr', 0xF067, 0x20),
    ('wr', 0xF0E5, 0x40), ('wr', 0xF0E5, 0x00), ('wr', 0xF0E6, 0x04),
    ('wr', 0xF04E, 0x00),
    ('wr', 0xD909, 0x55), ('wr', 0xD90A, 0x55), ('wr', 0xD906, 0x04),
    ('wr', 0xD905, 0x03), ('wr', 0xD904, 0xFE), ('wr', 0xD90B, 0x84),
    ('wr', 0xD90C, 0x30), ('wr', 0xF04C, 0x60), ('wr', 0xD929, 0x06),
]

# SPI-команды, которые тул готов послать. Только чтение состояния и данных;
# ни одного опкода записи/стирания здесь нет и быть не должно.
READ_OPCODES = {
    0x03: 'Read Data',
    0x0B: 'Fast Read',
    0x9F: 'RDID (JEDEC)',
    0x05: 'Read Status-1',
    0x35: 'Read Status-2',
    0xC8: 'Read Extended Address Register',
    0x4B: 'Read Unique ID',
    0x5A: 'Read SFDP',
}


def xor(slave, frame):
    x = slave
    for b in frame:
        x ^= b
    return x


def report04(sub, read_addr, write_addr, frame):
    """64-байтный HID-отчёт 0x04: заголовок, посылка [len][frame], XOR, добивка."""
    body = bytes([sub, read_addr, 0x00, write_addr, len(frame)]) + bytes(frame)
    body += bytes([xor(write_addr, bytes([len(frame)]) + bytes(frame))])
    return bytes([0x04]) + body + bytes(64 - 1 - len(body))


def auto_int(value):
    """Число CLI в обычной записи Python: 123, 0x7b, 0o173 или 0b1111011."""
    try:
        return int(value, 0)
    except ValueError as e:
        raise argparse.ArgumentTypeError(f'не число: {value!r}') from e


class Bridge:
    def __init__(self, dry_run=False, flash_read_method='auto'):
        if flash_read_method not in ('auto', 'legacy', '4a'):
            raise ValueError('неизвестный способ чтения flash')
        self.flash_read_method = flash_read_method
        self._flash_reader = None
        self._flash_discovery_done = False
        self.dry = dry_run
        self.dev = None
        if dry_run:
            return
        try:
            import hid
        except ImportError:
            sys.exit('нужен модуль hid: .venv/bin/pip install hidapi')
        # open() на macOS не всегда падает для отсутствующего устройства и потом
        # отдаёт мусор — поэтому сначала явно убеждаемся, что оно перечислено
        if not hid.enumerate(VID, PID):
            sys.exit(f'устройство {VID:04x}:{PID:04x} (U7005) не найдено — '
                     f'запускать надо на машине с подключённым монитором')
        self.hid = hid
        self.dev = hid.device()
        for attempt in range(20):
            try:
                self.dev.open(VID, PID)
                break
            except OSError:
                if attempt == 19:
                    raise
                time.sleep(0.1)
        self.dev.set_nonblocking(0)

    def _xfer(self, report, tag):
        """Послать отчёт 0x04 и вернуть ответ с той же подкомандой `tag`.

        Ответы приходят асинхронно, поэтому читаем до совпадения подкоманды,
        а не берём первый попавшийся отчёт — иначе пары запрос/ответ разъезжаются.
        """
        if self.dry:
            print(f'  → {report.rstrip(chr(0).encode()).hex(" ")}')
            return None
        self.dev.write(report)
        for _ in range(12):
            r = self.dev.read(64, timeout_ms=300)
            if r and r[0] == 0x04 and r[1] == tag:
                return bytes(r)
        raise TimeoutError(f'нет ответа на подкоманду {tag:#04x}')

    def enter_bridge_only(self):
        """Только вернуть мост U7005 в режим сырого I²C (`e0 01`), без хендшейка
        скалера. Годится, когда скалер УЖЕ в ISP-режиме от прошлого прогона
        (--reuse): чтение продолжается без повторного входа и без новой
        перезагрузки. Проверено 2026-08-16."""
        if self.dry:
            print('  → 01 e0 01  (только мост, скалер уже в ISP-режиме)')
            return
        self.dev.write(bytes([0x01, 0xE0, 0x01]) + b'\xff' * 61)
        r = self.dev.read(64, timeout_ms=500)
        if not r or bytes(r[:3]) != bytes([0x01, 0x5A, 0x01]):
            raise IOError(f'мост не ответил ({bytes(r[:3]).hex(" ") or "пусто"})')

    def heartbeat(self):
        """Локальный GET U7005: читает/сбрасывает Macro/Navi event, не проверяет UART."""
        if self.dry:
            print('  → 01 35 38 30 30 31 31 30 0d  (5800110\\r)')
            return b''
        request = bytes([0x01]) + b'5800110\r' + bytes(55)
        self.dev.write(request)
        for _ in range(12):
            response = bytes(self.dev.read(64, timeout_ms=300))
            if response and response[0] == 0x01 and b'\r' in response[1:]:
                body = response[1:response.index(b'\r', 1) + 1]
                if body.startswith(b'5b0011'):
                    return body
        raise TimeoutError('нет ответа на локальный heartbeat U7005 5800110')

    def reconnect_after_reset(self, timeout=20.0):
        """Переоткрыть U7005 после перезапуска домена скалера."""
        self._flash_reader = None
        self._flash_discovery_done = False
        if self.dry:
            return
        try:
            self.dev.close()
        except OSError:
            pass
        self.dev = None
        deadline = time.monotonic() + timeout
        last_error = None
        while time.monotonic() < deadline:
            if self.hid.enumerate(VID, PID):
                candidate = self.hid.device()
                try:
                    candidate.open(VID, PID)
                except OSError as e:
                    last_error = e
                else:
                    candidate.set_nonblocking(0)
                    self.dev = candidate
                    return
            time.sleep(0.25)
        raise TimeoutError(f'U7005 не перечислился после сброса: {last_error}')

    def enter(self):
        """Ввести монитор в ISP-режим. Это не пассивная операция:
        `exit()` сбрасывает только мост U7005, а для возврата скалера нужен
        отдельный `--recover` или передёргивание питания."""
        if self.dry:
            print('  → 01 35 38 30 30 34 30 3a 0d  (5 8 0040 : — UartSetI2CEnable)')
            print('  → 01 e0 01  (мост в режим сырого I²C)')
            print(f'  → блок инициализации из захвата: {len(SETUP)} команд '
                  '(a0, разблокировка, init 0xB0, регистры)')
            return
        # 1. кадр скалеру: включить I²C-мост (ответа нет — как в захвате)
        self.dev.write(bytes([0x01, 0x35, 0x38, 0x30, 0x30, 0x34, 0x30, 0x3A, 0x0D])
                       + bytes(55))
        time.sleep(0.3)
        # 2. переключить мост U7005 в режим отчёта 0x04
        self.dev.write(bytes([0x01, 0xE0, 0x01]) + b'\xff' * 61)
        r = self.dev.read(64, timeout_ms=500)
        if not r or bytes(r[:3]) != bytes([0x01, 0x5A, 0x01]):
            raise IOError(f'мост не ответил на вход ({bytes(r[:3]).hex(" ") or "пусто"})')
        time.sleep(1.5)   # дать скалеру уйти в ISP-режим до записей (как в захвате)
        self.play_setup()

    def enter_bootloader(self):
        """Продолжить вход, подготовленный bootloader-libre.

        Загрузчик уже включил USB-тракт, освободил service-UART и назначил
        raw-slave 0x6E. Поэтому хост переключает только U7005 в I2C и затем
        проигрывает тот же проверенный блок SETUP, что и обычный полный вход.
        """
        if self.dry:
            print('  -> 01 e0 01  (U7005: UART -> I2C; scaler prepared by bootloader)')
            print(f'  -> block SETUP: {len(SETUP)} commands')
            return
        self.dev.write(bytes([0x01, 0xE0, 0x01]) + b'\xff' * 61)
        r = self.dev.read(64, timeout_ms=500)
        if not r or bytes(r[:3]) != bytes([0x01, 0x5A, 0x01]):
            raise IOError(f'bridge did not enter I2C mode '
                          f'({bytes(r[:3]).hex(" ") or "empty"})')
        time.sleep(1.5)
        self.play_setup()

    def play_setup(self):
        """Проиграть блок инициализации из захвата в точном порядке.

        Вынесено из `enter()`, чтобы полный вход можно было доиграть поверх уже
        переключённого моста — например когда `580040:` и `e0 01` посланы вручную
        (`tools/burst_series.py --full`).
        """
        for step in SETUP:
            if step[0] == 'wr':
                self.write_reg(step[1], step[2])
            elif step[0] == 'rd':
                self.read_reg(step[1])
            else:  # raw-кадр на слейв 0x04/0xB0
                rep = self._xfer(step[1] + bytes(64 - len(step[1])), step[2])
                if rep[2] != 0x01:
                    raise IOError(f'шаг init {step[2]:#04x} не подтверждён: {bytes(rep[:8]).hex(" ")}')
            time.sleep(0.005)

    def enter_light(self):
        """Лёгкий вход: сеанс без остановки ядер, монитор продолжает работать.

        `580040:` → `e0 01` → `a0` с третьим байтом `0x36`. Блок SETUP не
        проигрывается, поэтому Leon2 Main и Sub не останавливаются: картинка,
        OSD и кнопки живут. Доступны только чтения регистров (`0x87`); SPI и
        флеш требуют полного `enter()`.

        **Окно около шести секунд.** Дальше скалер сбрасывается сам, и один раз
        из трёх это оставило монитор в тупиковом состоянии, откуда выводит
        только питание. Поэтому закрывать сеанс надо самому — `exit_light()`.

        Вход **из непроверенного состояния даёт тупик**: служебный UART
        выключается, а слейв не назначается. Поэтому базовая линия проверяется
        обязательно — но она **не гарантия**: 2026-08-26 вход сорвался в тупик и
        после успешной проверки. Если `a0` вернул признак `0x00`, монитор уже в
        тупике, и выводит из него только питание: ни повтор входа, ни commit
        `34 06 3c`, ни смена входа не помогают (`docs/ddc-external-probe.md`).
        """
        if self.dry:
            print('  → 01 35 38 30 30 31 31 30 0d  (базовая линия 5800110)')
            print('  → 01 35 38 30 30 34 30 3a 0d  (5 8 0040 : — UartSetI2CEnable)')
            print('  → 01 e0 01  (мост в режим сырого I²C)')
            print('  → 04 a0 6f 00 04 34 06 36  (a0: открыть сеанс, ждём a5 00)')
            return
        try:
            self.heartbeat()
        except TimeoutError:
            raise IOError('монитор не в чистом состоянии: служебный канал 58… молчит. '
                          'Вход из такого состояния даёт тупик — передёрните питание') from None
        self.dev.write(bytes([0x01, 0x35, 0x38, 0x30, 0x30, 0x34, 0x30, 0x3A, 0x0D])
                       + bytes(55))
        time.sleep(0.3)
        self.dev.write(bytes([0x01, 0xE0, 0x01]) + b'\xff' * 61)
        r = self.dev.read(64, timeout_ms=500)
        if not r or bytes(r[:3]) != bytes([0x01, 0x5A, 0x01]):
            raise IOError(f'мост не ответил на вход ({bytes(r[:3]).hex(" ") or "пусто"})')
        time.sleep(1.5)
        rep = self._xfer(SESSION_OPEN + bytes(64 - len(SESSION_OPEN)), 0xA0)
        # ожидаем 04 a0 01 00 6f 02 a5 00 c8
        if len(rep) < 9 or rep[2] != 0x01 or bytes(rep[5:8]) != b'\x02\xa5\x00':
            raise IOError(f'сеанс не открылся: {bytes(rep[:9]).hex(" ")}. '
                          f'Признак 0x00 означает, что слейв не назначен — только питание')

    def exit_light(self):
        """Штатный выход из лёгкого сеанса: `34 06 3c` — commit и перезагрузка.

        Тот же кадр, который штатная утилита шлёт подкомандой `a1` в конце
        сеанса. Монитор перезагружается немедленно и возвращается в рабочее
        состояние сам; ответа нет и быть не может.
        """
        if self.dry:
            print('  → 04 a0 6f 00 04 34 06 3c  (commit, монитор перезагрузится)')
            return
        if self.dev is None:
            return
        try:
            self.dev.write(SESSION_COMMIT + bytes(64 - len(SESSION_COMMIT)))
        except OSError:
            pass          # устройство уже могло исчезнуть — это и есть перезагрузка
        print('сеанс закрыт: монитор перезагружается, USB-мост вернётся через ~10 с',
              file=sys.stderr)

    def exit(self):
        if self.dry:
            print('  → 01 e0 00  (выход из режима)')
            return
        if self.dev is None:
            return
        try:
            self.dev.write(bytes([0x01, 0xE0, 0x00]) + b'\xff' * 61)
            time.sleep(0.2)
            self.dev.read(64, timeout_ms=300)
        except OSError:
            pass    # устройство могло исчезнуть вместе с перезагрузкой скалера

    def probe_reg_slave(self, rd, wr, reg=0xD511):
        """Опрос присутствия слейва подкомандой `aa` — читающей и документированной.

        Возвращает `(признак, сырой ответ)`. Признак — второй байт ответа, и его
        смысл документирован (`docs/ddc-external-probe.md`): `0x01` с данными —
        слейв отвечает и вооружён, `0x01` без данных — слейв есть, но не вооружён,
        `0x00` — NACK на адресной фазе, слейва нет.

        Прежние заходы 2026-08-30 брали подкоманду `c3` и оба раза не измерили
        ничего: `c3` — не проба присутствия, а чтение результата уже выполненной
        блочной операции.
        """
        frame = [OP_READ_REG, reg >> 8, reg & 0xFF]
        rep = self._xfer(report04(0xAA, rd, wr, frame), 0xAA)
        if self.dry:
            return None, b''
        return rep[2], bytes(rep[:9])

    def init_b0(self):
        """Кадр `04 bc 00 00 b0 ff 3d` — «init слейва 0xB0» из блока SETUP.

        Без него опрос бессмыслен: 2026-08-30 лёгкий сеанс `SETUP` не проигрывает,
        и `0xB1` молчал даже в положительном контроле. Смысл обвязки `FF 3D`
        неизвестен (`docs/nt68503-i2c-service-protocol.md`), поэтому это
        **единственная запись** во всём опросе, и она дословно из захвата штатного
        обновления.
        """
        frame = bytes.fromhex('04bc0000b0ff3d')
        if self.dry:
            print(f'  → {frame.hex(" ")}  (init слейва 0xB0)')
            return
        self._xfer(frame + bytes(64 - len(frame)), 0xBC)

    def probe_slave(self, read_addr=0xB1, write_addr=0xB0, count=5):
        """Чистое чтение `count` байт со слейва `read_addr` подкомандой `c3`.

        Кадр `04 c3 b1 00 b0 05` взят из захвата обновления (`tools/isp_block_transfer.py`,
        шаг «C3 poll»): на шину уходит только SLA+R, **слейву ничего не пишется**.
        Третий байт ответа — признак адресной фазы: `0x01` слейв подтвердил,
        `0x00` NACK (`docs/ddc-external-probe.md`).

        Возвращает `(признак, данные)`; при `dry_run` — `(None, b'')`.
        """
        report = bytes([0x04, 0xC3, read_addr, 0x00, write_addr, count])
        report += bytes(64 - len(report))
        if self.dry:
            print(f'  → {report[:6].hex(" ")}  '
                  f'(c3: чтение {count} байт со слейва {read_addr:#04x})')
            return None, b''
        rep = self._xfer(report, 0xC3)
        return rep[2], bytes(rep[5:5 + count])

    def write_reg(self, reg, val):
        frame = [OP_WRITE_REG, reg >> 8, reg & 0xFF, val]
        rep = self._xfer(report04(0xA9, RD, WR, frame), 0xA9)
        if self.dry:
            return
        # ответ: 04 a9 01 00 6f 01 87 xor
        if (len(rep) < 8 or rep[2] != 0x01 or rep[4] != RD or
                rep[5] != 1 or rep[6] != 0x87 or
                rep[7] != xor(rep[4], rep[5:7])):
            raise IOError(f'неожиданный ответ на запись регистра: '
                          f'{bytes(rep[:8]).hex(" ")}')

    def read_reg(self, reg):
        frame = [OP_READ_REG, reg >> 8, reg & 0xFF]
        rep = self._xfer(report04(0xAA, RD, WR, frame), 0xAA)
        if self.dry:
            return 0
        # ответ: 04 aa 01 00 6f 02 78 <val> xor
        if (len(rep) < 9 or rep[2] != 0x01 or rep[4] != RD or
                rep[5] != 2 or rep[6] != 0x78 or
                rep[8] != xor(rep[4], rep[5:8])):
            raise IOError(f'неожиданный ответ на чтение регистра: '
                          f'{bytes(rep[:9]).hex(" ")}')
        return rep[7]

    def ahb_read32(self, addr):
        """Прочитать одно выровненное 32-битное слово через PBus→AHB bridge.

        Это не прямой opcode service slave: 0x78/0x87 настраивают регистры моста,
        а уже тот делает один AHB read. Последовательность повторяет FUN_CD27 8051,
        но вместо его бесконечного ожидания имеет конечное число опросов.
        """
        if not 0 <= addr <= 0xFFFFFFFF:
            raise ValueError(f'AHB-адрес вне 32-битного диапазона: {addr:#x}')
        if addr & 3:
            raise ValueError(f'AHB read32 требует адрес, кратный 4: {addr:#x}')

        state = self.read_reg(AHB_CTRL)
        if not self.dry and not state & AHB_READY:
            raise IOError(f'PBus→AHB bridge не готов перед чтением {addr:#010x}: '
                          f'CD8C={state:#04x}')

        # FUN_CD27: CD80 = address[7:0], ..., CD83 = address[31:24].
        for i in range(4):
            self.write_reg(AHB_ADDR + i, (addr >> (i * 8)) & 0xFF)
        self.write_reg(AHB_CTRL, AHB_START)

        if self.dry:
            # Показать один кадр опроса и все четыре чтения результата.
            self.read_reg(AHB_CTRL)
            raw = bytes(self.read_reg(AHB_DATA + i) for i in range(4))
            return raw[::-1]

        state = 0
        for _ in range(AHB_POLL_LIMIT):
            state = self.read_reg(AHB_CTRL)
            if state & AHB_READY:
                break
            time.sleep(0.001)
        else:
            raise TimeoutError(f'PBus→AHB timeout при чтении {addr:#010x}: '
                               f'CD8C={state:#04x}; требуется power cycle')

        # CD88 содержит младший байт слова. Штатный FUN_CD27 читает все четыре
        # регистра по порядку; чтение CD8B завершает транзакцию моста.
        raw = bytes(self.read_reg(AHB_DATA + i) for i in range(4))
        return raw[::-1]

    def ahb_write32(self, addr, value):
        """Записать одно выровненное 32-битное слово через PBus→AHB bridge.

        CLI общего назначения для этого примитива намеренно нет: он нужен только
        внутреннему read-only драйверу U4003 для управления GPIO.
        """
        if not 0 <= addr <= 0xFFFFFFFF or addr & 3:
            raise ValueError(f'AHB write32 требует выровненный 32-битный адрес: {addr:#x}')
        if not 0 <= value <= 0xFFFFFFFF:
            raise ValueError(f'AHB-значение вне 32 бит: {value:#x}')

        state = self.read_reg(AHB_CTRL)
        if not self.dry and not state & AHB_READY:
            raise IOError(f'PBus→AHB bridge не готов перед записью {addr:#010x}: '
                          f'CD8C={state:#04x}')

        for i in range(4):
            self.write_reg(AHB_ADDR + i, (addr >> (i * 8)) & 0xFF)
            self.write_reg(AHB_WDATA + i, (value >> (i * 8)) & 0xFF)
        self.write_reg(AHB_CTRL, AHB_WRITE_START)

        if self.dry:
            self.read_reg(AHB_CTRL)
            return

        state = 0
        for _ in range(AHB_POLL_LIMIT):
            state = self.read_reg(AHB_CTRL)
            if state & AHB_READY:
                return
            time.sleep(0.001)
        raise TimeoutError(f'PBus→AHB timeout при записи {addr:#010x}: '
                           f'CD8C={state:#04x}; требуется power cycle')

    def verify_ahb_write(self):
        """Проверить write primitive на RAM и обязательно вернуть исходное слово."""
        original = int.from_bytes(self.ahb_read32(AHB_WRITE_PROBE), 'big')
        probe = original ^ 0xA55AA55A
        restored = False
        try:
            self.ahb_write32(AHB_WRITE_PROBE, probe)
            if not self.dry:
                got = int.from_bytes(self.ahb_read32(AHB_WRITE_PROBE), 'big')
                if got != probe:
                    raise IOError(f'AHB write probe не сохранился: записано {probe:#010x}, '
                                  f'прочитано {got:#010x}')
        finally:
            self.ahb_write32(AHB_WRITE_PROBE, original)
            if self.dry:
                restored = True
            else:
                restored = int.from_bytes(self.ahb_read32(AHB_WRITE_PROBE), 'big') == original
        if not restored:
            raise IOError(f'не удалось восстановить AHB probe по {AHB_WRITE_PROBE:#010x}; '
                          'требуется power cycle')

    def read_ahb(self, addr, length):
        """Прочитать произвольный диапазон AHB, включая невыравненные края."""
        if not 0 <= addr <= 0xFFFFFFFF:
            raise ValueError(f'AHB-адрес вне 32-битного диапазона: {addr:#x}')
        if length < 0 or addr + length > 0x100000000:
            raise ValueError(f'AHB-диапазон вне 32-битного пространства: '
                             f'{addr:#x}+{length:#x}')
        if length == 0:
            return b''

        aligned = addr & ~3
        end = (addr + length + 3) & ~3
        data = bytearray()
        for word_addr in range(aligned, end, 4):
            data += self.ahb_read32(word_addr)
        offset = addr - aligned
        return bytes(data[offset:offset + length])

    def spi(self, send, recv_len):
        """Исполнить одну SPI-команду: отправить байты send, принять recv_len.

        Первый байт send — опкод, и он обязан быть в белом списке чтения.
        Окно 0xA700 — 256 байт, приём с A707, поэтому больше 249 байт наложится
        на управляющие регистры и вернёт мусор (проверено 2026-08-16).
        """
        if send[0] not in READ_OPCODES:
            raise ValueError(f'опкод {send[0]:#04x} не в списке чтения — отказ')
        if len(send) + recv_len > 0xFF:
            raise ValueError(f'{len(send)}+{recv_len} байт не влезают в окно A700 (макс 255)')
        base = A700
        buf = base + 2
        recv = buf + len(send)
        # окно
        self.write_reg(F0C0 + 0, 0x13)
        self.write_reg(F0C0 + 1, base >> 8)
        self.write_reg(F0C0 + 2, base & 0xFF)
        self.write_reg(F0C0 + 3, buf >> 8)
        self.write_reg(F0C0 + 4, buf & 0xFF)
        self.write_reg(F0C0 + 5, recv >> 8)
        self.write_reg(F0C0 + 6, recv & 0xFF)
        # длины и байты команды
        self.write_reg(base + 0, len(send))
        self.write_reg(base + 1, recv_len)
        for i, b in enumerate(send):
            self.write_reg(buf + i, b)
        # запуск и обязательная пауза: движку нужно ~0.25 с, иначе читается мусор
        self._xfer(report04(0xAF, RD, WR, [OP_SPI_RUN]), 0xAF)
        if not self.dry:
            time.sleep(0.25)
        # результат
        return bytes(self.read_reg(recv + i) for i in range(recv_len))

    def jedec(self):
        return self.spi([0x9F], 3)

    def read_flash(self, addr, length, chunk=249):
        """Read an offset in the current EAR bank, preserving the legacy API.

        4A uses absolute addresses and selects the ISP bank itself. Read EAR
        afresh rather than assuming bank zero or caching another caller's state.
        Only discovery failure allows auto fallback; page/transport errors abort.
        """
        validate_flash_read_range(addr, length, chunk)
        if length == 0:
            return b''
        reader = self.flash_reader()
        if reader is not None:
            bank = self.spi([0xC8], 1)[0]
            if bank not in (0, 1):
                raise ValueError(f'RDEAR={bank:02x}: банк вне 32-МиБ U4002')
            return b''.join(reader.read((bank << 24) | addr, length))
        out = bytearray()
        chunk = min(chunk, 249)      # предел окна A700
        while length:
            n = min(chunk, length)
            send = [0x0B, (addr >> 16) & 0xFF, (addr >> 8) & 0xFF, addr & 0xFF, 0x00]
            out += self.spi(send, n)
            addr += n
            length -= n
        return bytes(out)

    def flash_reader(self):
        """Discover 4A once per connection; never send it to an old bridge."""
        if self.dry or self.flash_read_method == 'legacy':
            return None
        if not self._flash_discovery_done:
            reader = FlashReader(self.dev)
            try:
                reader.discover()
            except (TimeoutError, UnsupportedExtensionError) as error:
                if self.flash_read_method == '4a':
                    raise
                print(f'flash read: legacy SPI ({error})', file=sys.stderr)
            else:
                self._flash_reader = reader
                print('flash read: U7EX 0x4A', file=sys.stderr)
            self._flash_discovery_done = True
        if self._flash_reader is None and self.flash_read_method == '4a':
            raise UnsupportedExtensionError('расширение 4A не обнаружено в этом сеансе')
        return self._flash_reader

    def restart_leon2(self, ctrl):
        """Штатный STOP, затем дословная двухфазная RUN-последовательность 8051."""
        self.ahb_write32(ctrl, LEON2_STOP)
        value = int.from_bytes(self.ahb_read32(ctrl), 'big')
        self.ahb_write32(ctrl, value | LEON2_RUN_SET)
        value = int.from_bytes(self.ahb_read32(ctrl), 'big')
        self.ahb_write32(ctrl, value & ~LEON2_RUN_CLEAR)
        return int.from_bytes(self.ahb_read32(ctrl), 'big')

    def sample_recovery_state(self, delay=0.5):
        main_ctrl = int.from_bytes(self.ahb_read32(LEON2_MAIN_CTRL), 'big')
        sub_ctrl = int.from_bytes(self.ahb_read32(LEON2_SUB_CTRL), 'big')
        main_tick_1 = int.from_bytes(self.ahb_read32(LEON2_MAIN_TICK), 'big')
        stbc_tick_1 = self.read_reg(STBC_TIMER0_TICK)
        if not self.dry:
            time.sleep(delay)
        main_tick_2 = int.from_bytes(self.ahb_read32(LEON2_MAIN_TICK), 'big')
        stbc_tick_2 = self.read_reg(STBC_TIMER0_TICK)
        return (main_ctrl, sub_ctrl, main_tick_1, main_tick_2,
                stbc_tick_1, stbc_tick_2)


class EEPROMReader:
    """Только чтение U4003 через GPIO bank 4; EEPROM-write API отсутствует."""

    def __init__(self, bridge):
        self.bridge = bridge
        self.original_data = int.from_bytes(bridge.ahb_read32(EEPROM_GPIO_DATA), 'big')
        self.original_dir = int.from_bytes(bridge.ahb_read32(EEPROM_GPIO_DIR), 'big')
        self.data = self.original_data
        self.direction = self.original_dir
        self.closed = False

    def _write_data(self, value):
        value &= 0xFFFFFFFF
        if value != self.data:
            self.bridge.ahb_write32(EEPROM_GPIO_DATA, value)
            self.data = value

    def _write_dir(self, value):
        value &= 0xFFFFFFFF
        if value != self.direction:
            self.bridge.ahb_write32(EEPROM_GPIO_DIR, value)
            self.direction = value

    def _drive_low(self, mask):
        # Повторяет GPIO_Write(value=0), затем GPIO_Dir(output=0) штатного runtime.
        self._write_data((self.data | self.direction) & ~mask)
        self._write_dir(self.direction & ~mask)

    def _release(self, mask):
        # Повторяет GPIO_Write(value=1), затем GPIO_Dir(input=1): open-drain high.
        self._write_data((self.data | self.direction) | mask)
        self._write_dir(self.direction | mask)

    def _sample(self):
        if self.bridge.dry:
            # В dry-run нет физического input: достаточно моделировать отпущенные
            # линии high, а ACK отдельно принимается условно ниже.
            return self.data | EEPROM_SCL
        return int.from_bytes(self.bridge.ahb_read32(EEPROM_GPIO_DATA), 'big')

    def _clock_high(self):
        self._release(EEPROM_SCL)
        sample = 0
        for _ in range(EEPROM_CLOCK_POLL_LIMIT):
            sample = self._sample()
            if sample & EEPROM_SCL:
                return sample
            time.sleep(0.001)
        raise TimeoutError('U4003 держит SCL low (clock stretching/bus stuck)')

    def _clock_low(self):
        self._drive_low(EEPROM_SCL)

    def _start(self):
        self._release(EEPROM_SDA)
        sample = self._clock_high()
        if not sample & EEPROM_SDA:
            raise IOError('шина U4003 занята: SDA low перед START')
        self._drive_low(EEPROM_SDA)
        self._clock_low()

    def _stop(self):
        self._drive_low(EEPROM_SDA)
        self._clock_high()
        self._release(EEPROM_SDA)

    def _send_byte(self, value, what):
        for bit in range(7, -1, -1):
            (self._release if value & (1 << bit) else self._drive_low)(EEPROM_SDA)
            self._clock_high()
            self._clock_low()
        self._release(EEPROM_SDA)
        sample = self._clock_high()
        ack = self.bridge.dry or not bool(sample & EEPROM_SDA)
        self._clock_low()
        if not ack:
            raise IOError(f'U4003 не подтвердила {what} ({value:#04x})')

    def _read_byte(self, nack):
        value = 0
        self._release(EEPROM_SDA)
        for _ in range(8):
            value = (value << 1) | bool(self._clock_high() & EEPROM_SDA)
            self._clock_low()
        (self._release if nack else self._drive_low)(EEPROM_SDA)
        self._clock_high()
        self._clock_low()
        self._release(EEPROM_SDA)
        return value

    def random_read(self, slave, offset, length):
        validate_eeprom_range(slave, offset, length)
        if length == 0:
            return b''
        started = False
        stopped = False
        try:
            self._start()
            started = True
            self._send_byte(slave << 1, 'адрес write')
            self._send_byte(offset >> 8, 'старший байт смещения')
            self._send_byte(offset & 0xFF, 'младший байт смещения')
            self._start()  # repeated START; STOP после offset не посылается
            self._send_byte((slave << 1) | 1, 'адрес read')
            data = bytes(self._read_byte(nack=i == length - 1) for i in range(length))
            self._stop()
            stopped = True
            return data
        finally:
            if started and not stopped:
                try:
                    self._stop()
                except Exception:
                    pass

    def close(self):
        if self.closed:
            return
        self.closed = True
        # Сначала отпустить обе линии, затем восстановить защёлку и направление.
        self._release(EEPROM_SCL | EEPROM_SDA)
        self._write_data(self.original_data)
        self._write_dir(self.original_dir)


def validate_eeprom_range(slave, offset, length):
    if slave not in EEPROM_ADDRS:
        raise ValueError(f'U4003 разрешена только по 0x50/0x58, не {slave:#x}')
    if offset < 0 or length <= 0:
        raise ValueError('смещение должно быть неотрицательным, длина U4003 — больше нуля')
    if slave == 0x50 and offset + length <= 0x8000:
        return
    if slave == 0x58 and ((offset <= 0x40 and offset + length <= 0x40) or
                          (offset == 0xC000 and length <= 1)):
        return
    raise ValueError(f'неразрешённый диапазон U4003: slave={slave:#04x}, '
                     f'offset={offset:#06x}, length={length:#x}')


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--jedec', action='store_true', help='прочитать JEDEC ID и выйти')
    g.add_argument('--read', nargs=2, type=auto_int, metavar=('АДРЕС', 'ДЛИНА'),
                   help='прочитать диапазон флеша (числа с 0x или без)')
    g.add_argument('--ahb-read', nargs=2, type=auto_int, metavar=('АДРЕС', 'ДЛИНА'),
                   help='экспериментально прочитать 32-битное пространство Leon2 '
                        'через PBus→AHB')
    g.add_argument('--reg-read', nargs=2, type=auto_int, metavar=('АДРЕС', 'ДЛИНА'),
                   help='прочитать XDATA/регистры 8051 через service slave 0x6E')
    g.add_argument('--eeprom-read', nargs=3, type=auto_int,
                   metavar=('SLAVE', 'СМЕЩЕНИЕ', 'ДЛИНА'),
                   help='прочитать U4003 через GPIO-I2C (только 0x50/0x58; '
                        'EEPROM-write команд нет)')
    g.add_argument('--probe-buffer', action='store_true',
                   help='нащупать размер приёмного окна, увеличивая chunk')
    g.add_argument('--probe-reset', action='store_true',
                   help='отвечает ли служебная шина в окне сброса: только e0 01 и '
                        'опрос 0x6E/0xB0 в цикле, пока оператор жмёт SW4101. '
                        'Ничего прошивочного не шлётся, только чтение')
    g.add_argument('--probe-gate', action='store_true',
                   help='какая запись из SETUP открывает слейва 0xB0: три записи в '
                        'лёгком сеансе с опросом после каждой, ядра не глушатся')
    g.add_argument('--probe-b0', action='store_true',
                   help='отвечает ли слейв 0xB0 БЕЗ прошивочного вооружения. Только '
                        'чтение подкомандой c3, слейву ничего не пишется; три стадии')
    g.add_argument('--heartbeat', action='store_true',
                   help='опросить/сбросить Macro/Navi event U7005 (5800110); UART не проверяет')
    g.add_argument('--restart-leon2', action='store_true',
                   help='экспериментально выполнить штатные STOP/RUN для Main и Sub')
    g.add_argument('--recover', action='store_true',
                   help='выйти из ISP: завершённое окно FW.034 — пуск STBC; '
                        'пустое окно bootloader recovery — watchdog reset; '
                        'после сброса проверить UART-транспорт')
    ap.add_argument('-o', '--out',
                    help='файл для --read/--ahb-read/--eeprom-read (иначе hex)')
    ap.add_argument('--chunk', type=int, default=249,
                    help='байт за одну SPI-команду (по умолчанию и максимум 249 — '
                         'предел окна A700, проверен побайтовой сверкой)')
    ap.add_argument('--dry-run', action='store_true',
                    help='печатать кадры, ничего не слать и не открывать устройство')
    ap.add_argument('--light', action='store_true',
                    help='лёгкий вход: без остановки ядер, монитор продолжает '
                         'работать; только с --reg-read, окно ~6 с, выход штатный')
    ap.add_argument('--seconds', type=float, default=180.0,
                    help='длительность прогона --probe-reset, с (по умолчанию 180)')
    ap.add_argument('--no-unlock', action='store_true',
                    help='с --probe-gate: писать только 0xF055, без 0xF0E0/0xF0E2 = '
                         '0xAA. Проверяет, нужна ли разблокировка вообще')
    ap.add_argument('--full', action='store_true',
                    help='добавить к --probe-b0 стадию D: полный вход с блоком SETUP, '
                         'единственный положительный контроль на сам 0xB0. '
                         'Останавливает монитор, выход через --recover --reuse')
    ap.add_argument('--reuse', action='store_true',
                    help='скалер уже в ISP-режиме от прошлого прогона — не повторять '
                         'вход, только вернуть мост (без новой перезагрузки)')
    ap.add_argument('--bootloader', action='store_true',
                    help='bootloader-libre уже удерживает recovery: не посылать '
                         '580040, переключить U7005 в I2C и проиграть SETUP')
    add_flash_read_argument(ap)
    args = ap.parse_args()

    if args.read:
        try:
            validate_flash_read_range(*args.read, chunk=args.chunk)
        except ValueError as error:
            ap.error(str(error))

    # Проверить опасные экспериментальные диапазоны до открытия USB и входа в ISP.
    if args.ahb_read:
        addr, length = args.ahb_read
        if not 0 <= addr <= 0xFFFFFFFF:
            ap.error(f'AHB-адрес вне 32-битного диапазона: {addr:#x}')
        if length < 0 or addr + length > 0x100000000:
            ap.error(f'AHB-диапазон вне 32-битного пространства: '
                     f'{addr:#x}+{length:#x}')
    if args.eeprom_read:
        try:
            validate_eeprom_range(*args.eeprom_read)
        except ValueError as e:
            ap.error(str(e))
    if args.light:
        if not args.reg_read:
            ap.error('--light работает только с --reg-read: без блока SETUP доступны '
                     'лишь чтения регистров, а SPI и флеш требуют полного входа')
        if args.reuse:
            ap.error('--light и --reuse несовместимы: лёгкий вход всегда начинается '
                     'с чистого состояния')
        if args.bootloader:
            ap.error('--light и --bootloader несовместимы')

    if args.reuse and args.bootloader:
        ap.error('--reuse и --bootloader несовместимы')

    if args.probe_b0 and (args.light or args.reuse or args.bootloader):
        ap.error('--probe-b0 сам управляет стадиями входа: --light, --reuse и '
                 '--bootloader не нужны')

    br = Bridge(dry_run=args.dry_run, flash_read_method=args.flash_read_method)
    try:
        if args.probe_reset:
            br.enter_bridge_only()
            try:
                probe_reset(br, seconds=args.seconds)
            finally:
                if br.dev is not None:
                    br.exit()
            return
        if args.probe_gate:
            probe_gate(br, unlock=not args.no_unlock)
            return
        if args.probe_b0:
            probe_b0(br, full=args.full)   # сам управляет входом и выходом
            return
        if args.heartbeat:
            reply = br.heartbeat()
            if not br.dry:
                print(reply.rstrip(b'\r').decode('ascii', errors='backslashreplace'))
            return
        try:
            if args.light:
                br.enter_light()
            elif args.bootloader:
                br.enter_bootloader()
            else:
                br.enter_bridge_only() if args.reuse else br.enter()
        except (IOError, OSError) as e:
            sys.exit(f'нет связи с мостом: {e}')
        try:
            _run(br, args)
        except RecoveryVerificationUnavailable as error:
            print(str(error), file=sys.stderr)
            raise SystemExit(2) from None
    finally:
        if not args.probe_b0:
            br.exit_light() if args.light else br.exit()


def probe_b0(br, full=False):
    """Отвечает ли слейв `0xB0` — опрос подкомандой `aa`, с контролем в каждой стадии.

    Третий заход. Два прежних не измерили ничего, и оба раза по одной причине:
    инструмент опроса был выбран неверно, а понять это можно было только по
    контролю. Поэтому здесь **в каждой стадии опрашиваются оба слейва** — искомый
    `0xB1`/`0xB0` и заведомо живой `0x6F`/`0x6E`. Если контроль молчит, стадия
    недействительна, и это видно сразу, а не в конце.

    Стадии разводят прошивочное и аппаратное:

    A. только `e0 01` — пады **моста** в I²C, скалера не касаемся;
    B. `580040:` + `e0 01` — прошивка скалера подготовила служебный интерфейс;
    C. полный лёгкий вход с `a0` — здесь контроль обязан ответить `0x01` с данными.

    Пишущего нет ничего: `aa` — читающая подкоманда.
    """
    rows = []

    def stage(name):
        b0 = br.probe_reg_slave(0xB1, 0xB0)
        ctl = br.probe_reg_slave(RD, WR)
        if br.dry:
            return
        fmt = lambda f: {0x01: 'ОТВЕТИЛ', 0x00: 'нет (NACK)'}.get(f, f'признак {f:#04x}')
        print(f'  {name}: 0xB0 → {fmt(b0[0])}   контроль 0x6E → {fmt(ctl[0])}')
        print(f'      сырьё 0xB0: {b0[1].hex(" ")}')
        print(f'      сырьё 0x6E: {ctl[1].hex(" ")}')
        rows.append((name, b0[0], ctl[0]))

    print('Опрос 0xB0 подкомандой aa. В каждой стадии рядом опрашивается 0x6E —\n'
          'если контроль молчит, стадия недействительна.\n')

    print('A. только мост в I²C (e0 01), скалера не касаемся')
    br.enter_bridge_only()
    time.sleep(0.3)
    stage('A')
    br.exit()
    time.sleep(1.0)

    print('\nB. UartSetI2CEnable + мост, но без a0')
    br.heartbeat()
    if br.dry:
        print('  → 01 35 38 30 30 34 30 3a 0d  (5 8 0040 :)')
    else:
        br.dev.write(bytes([0x01, 0x35, 0x38, 0x30, 0x30, 0x34, 0x30, 0x3A, 0x0D])
                     + bytes(55))
    time.sleep(0.3)
    br.enter_bridge_only()
    time.sleep(1.5)
    stage('B')

    print('\nC. полный лёгкий вход с a0 — контроль здесь обязан ответить')
    try:
        rep = br._xfer(SESSION_OPEN + bytes(64 - len(SESSION_OPEN)), 0xA0)
        if not br.dry and (len(rep) < 9 or rep[2] != 0x01):
            print(f'  сеанс не открылся: {bytes(rep[:9]).hex(" ")}')
        stage('C')
    finally:
        br.exit_light()

    if full:
        # Стадия D — положительный контроль на сам 0xB0. Только здесь проигрывается
        # блок SETUP, а в нём init слейва 0xB0 и разблокировка контроллера; именно
        # в этом состоянии 0xB1 отвечает в штатном обновлении. Если и тут молчит —
        # опрос слепой, и все отрицательные результаты выше ничего не стоят.
        print('\nD. полный вход enter() с блоком SETUP — контроль на сам 0xB0')
        print('   монитор остановится; выход — isp_read.py --recover --reuse')
        if not br.dry:
            time.sleep(12)          # дождаться возврата моста после перезагрузки
            br.reconnect_after_reset()
        br.enter()
        stage('D')

    if br.dry:
        return
    print('\nЧто это значит:')
    valid = [r for r in rows if r[2] == 0x01]
    if not valid:
        print('  контроль не ответил ни в одной стадии — опыт снова ничего не измерил,')
        print('  разбираться надо с установкой, а не с выводом.')
        return
    first = next((r for r in rows if r[1] == 0x01), None)
    if first is None:
        print('  0xB0 молчит везде, где транспорт заведомо работает.')
        print('  ВНИМАНИЕ: это ещё не значит, что его нет. Положительного контроля')
        print('  на сам 0xB0 в этих стадиях не было — он отвечает в штатном')
        print('  обновлении только после полного блока SETUP, а лёгкий вход его не')
        print('  проигрывает. Нужна стадия D: --probe-b0 --full.')
    elif first[0] == 'A':
        print('  0xB0 отвечает БЕЗ участия прошивки скалера — необходимое условие')
        print('  канала восстановления выполнено.')
    else:
        print(f'  0xB0 появляется только начиная со стадии {first[0]}, то есть его')
        print('  поднимает прошивка. При мёртвом флеше его не будет.')


def probe_reset(br, seconds=180.0):
    """Отвечает ли служебная шина в окне сброса, до подъёма прошивки.

    Единственная оставшаяся ниточка к восстановлению без пайки. Оба звена цепочки,
    которые при работающей прошивке ставит она сама, имеют неизвестное состояние по
    сбросу:

    * **пады скалера** — при работе они в UART, в I²C их переводит
      `UartSetI2CEnable`; каково исходное состояние, не установлено;
    * **`0xF055`** — рабочее значение `0x06` пишет `stbc-main` в процедуре
      «Initial CC PHY», а загрузчик регистр не трогает вовсе
      (`docs/nt68503-hardware.md`). Значение по сбросу неизвестно, и если оно
      допускает `0xB0` — на мёртвом флеше слейв поднимется сам.

    Поэтому здесь **не делается ничего прошивочного**: ни `580040:`, ни `a0`. Только
    `e0 01` — переключение падов самого моста, — и опрос `0x6E` и `0xB0` в цикле,
    пока оператор жмёт `SW4101`.

    Отдельно различается «слейв молчит» и «мост отвалился»: `e0 01` переспрашивается
    и его ответ служит признаком живого моста. Без этого получился бы очередной
    прогон без контроля.
    """
    print('Опрос служебной шины в окне сброса. Ничего прошивочного не шлётся.')
    print(f'Жмите SW4101 два-три десятка раз в течение {seconds:g} с; Ctrl-C — выход.\n')

    def revive():
        """Вернуть мост. Отдельная функция, потому что reconnect_after_reset
        обнуляет `dev` и при неудаче оставляет его None — тогда следующий вызов
        падает по AttributeError, а не по OSError. Первый прогон 2026-08-30
        свалился ровно на этом."""
        try:
            br.reconnect_after_reset(timeout=8.0)
            return br.dev is not None
        except Exception:
            return False

    t0 = time.time()
    rounds = hits = lost = resync = dead = quiet = 0
    last_sync = 0.0
    try:
        while time.time() - t0 < seconds:
            now = time.time() - t0
            if br.dev is None:
                dead += 1
                if not revive():
                    time.sleep(0.5)
                    continue
                last_sync = 0.0
            if now - last_sync > 0.5:
                # Переспросить режим моста: он же и признак, что мост жив. Если
                # U7005 пережил сброс, ответ придёт; если нет — поймаем ошибку.
                try:
                    br.enter_bridge_only()
                    resync += 1
                except TimeoutError:
                    quiet += 1
                except OSError:
                    lost += 1
                    revive()
                last_sync = now
            try:
                b0 = br.probe_reg_slave(0xB1, 0xB0)
                ctl = br.probe_reg_slave(RD, WR)
            except TimeoutError:
                # Мост не ответил — но это ещё не значит, что он умер: скалер
                # мог в этот момент сбрасываться. Закрывать устройство здесь
                # нельзя, иначе сами себе устраиваем потерю связи; первый прогон
                # 2026-08-30 свалился именно так.
                quiet += 1
                continue
            except OSError:
                lost += 1
                revive()
                continue
            rounds += 1
            for name, r in (('0xB0', b0), ('0x6E', ctl)):
                if r[0] not in (0x00, None):
                    hits += 1
                    print(f'{time.time()-t0:8.3f}  {name} ОТВЕТИЛ: {r[1].hex(" ")}')
    except KeyboardInterrupt:
        pass

    dt = time.time() - t0
    print(f'\n# проходов {rounds} за {dt:.1f} с ({rounds/max(dt,1e-9):.0f}/с), '
          f'подтверждений {hits}, пересинхронизаций {resync}, '
          f'молчаний моста {quiet}, потерь устройства {lost}, '
          f'циклов без устройства {dead}')
    print('# «молчание» — мост на месте, но не ответил; «потеря» — устройство '
          'исчезло с USB. Различать обязательно: первое бывает при сбросе скалера '
          'и лечится ожиданием, второе означает, что мосту нужно внешнее питание.')
    if hits == 0:
        print('# Ни один адрес не подтвердился. Если потерь моста тоже ноль, значит')
        print('# опрос шёл всё время и по сбросу служебная шина недоступна: пады не')
        print('# в I²C, либо 0xF055 по сбросу слейва не допускает. Если потерь много —')
        print('# мост не переживает SW4101, и его надо питать снаружи от CN7003.')


def probe_gate(br, unlock=True):
    """Какая именно запись из `SETUP` открывает слейва `0xB0`.

    Опыт 2026-08-30 показал, что `0xB0` не подтверждает адрес до блока `SETUP` и
    подтверждает после. Что стоит за адресом — прошивочный слейв или аппаратный блок
    с регистровым затвором, — из этого не следует
    (`docs/nt68503-i2c-service-protocol.md`, § «`0xB0` поднимает прошивка»).

    Здесь из всего `SETUP` берутся только три записи, идущие до init-кадра, и после
    каждой опрашивается `0xB0`. Если он откроется — затвор локализован, и версия
    «аппаратный блок» подтверждается. Ядра не останавливаются, картинка живёт.

    Записи ровно те, что делает штатная утилита. Записи регистров в лёгком сеансе
    проверены живьём 2026-08-26 (`docs/mcu-u7005.md`).
    """
    steps = [('исходно', None)]
    if unlock:
        steps += [('после 0xF0E0 = 0xAA', (0xF0E0, 0xAA)),
                  ('после 0xF0E2 = 0xAA', (0xF0E2, 0xAA))]
    steps += [('после 0xF055 = 0x01', (0xF055, 0x01))]

    print('Локализация затвора 0xB0: '
          + ('три записи из SETUP' if unlock
             else 'ТОЛЬКО 0xF055, без разблокировки 0xF0E0/0xF0E2')
          + ', опрос после каждой\n')
    br.enter_light()
    try:
        for label, wr in steps:
            if wr:
                br.write_reg(*wr)
                time.sleep(0.2)
            b0 = br.probe_reg_slave(0xB1, 0xB0)
            ctl = br.probe_reg_slave(RD, WR)
            # Чтение обратно различает «запись не прошла из-за защиты» и «прошла, но
            # затвор в другом месте» — без него отрицательный результат двусмыслен.
            back = br.read_reg(0xF055)
            if br.dry:
                continue
            fmt = lambda f: {0x01: 'ОТВЕТИЛ', 0x00: 'нет'}.get(f, f'{f:#04x}')
            print(f'  {label:22}  0xB0 → {fmt(b0[0])}   контроль → {fmt(ctl[0])}'
                  f'   0xF055 = {back:#04x}')
            print(f'      сырьё 0xB0: {b0[1].hex(" ")}')
            if b0[0] == 0x01:
                print('\n  ЗАТВОР ОТКРЫТ на этом шаге — версия «аппаратный блок с')
                print('  регистровым затвором» подтверждена, и затвор локализован.')
                return
    finally:
        br.exit_light()
    if not br.dry:
        print('\n  0xB0 не открылся. Смотреть на прочитанный обратно 0xF055: если он')
        print('  остался нулём — запись не прошла (защита); если стал единицей —')
        print('  прошла, и затвор в другом месте SETUP.')


def _run(br, args):
    if args.jedec:
        jid = br.jedec()
        if args.dry_run:
            return
        print('JEDEC ID:', jid.hex(' '),
              '(GD25Q256, 32 МБ — ожидаемо)' if jid == b'\xc8\x40\x19'
              else '← НЕ C8 40 19, остановиться')
    elif args.probe_buffer:
        print('нащупываю приёмное окно чтением Fast Read разной длины:')
        for n in (3, 8, 16, 32, 64, 128, 250):
            try:
                r = br.spi([0x0B, 0, 0, 0, 0], n)
                print(f'  recv {n:3d}: ok  {r[:8].hex(" ")}…')
            except (IOError, OSError) as e:
                print(f'  recv {n:3d}: сбой ({e}) — предел ниже')
                break
    elif args.read:
        addr, length = args.read
        data = br.read_flash(addr, length, chunk=args.chunk)
        if args.dry_run:
            return
        if args.out:
            with open(args.out, 'wb') as f:
                f.write(data)
            print(f'{len(data)} байт с {addr:#x} → {args.out}')
        else:
            print(data.hex(' '))
    elif args.eeprom_read:
        slave, offset, length = args.eeprom_read
        br.verify_ahb_write()
        reader = EEPROMReader(br)
        try:
            data = reader.random_read(slave, offset, length)
        finally:
            reader.close()
        if br.dry:
            return
        if args.out:
            with open(args.out, 'wb') as f:
                f.write(data)
            print(f'{len(data)} байт U4003 {slave:#04x}:{offset:#06x} → {args.out}')
        else:
            print(data.hex(' '))
    elif args.reg_read:
        addr, length = args.reg_read
        if not 0 <= addr <= 0xFFFF or length < 0 or addr + length > 0x10000:
            raise ValueError(f'регистровый диапазон вне 16 бит: {addr:#x}+{length:#x}')
        data = bytes(br.read_reg(addr + i) for i in range(length))
        if br.dry:
            return
        print(data.hex(' '))
    elif args.restart_leon2:
        br.verify_ahb_write()
        before = br.sample_recovery_state()
        print_recovery_state('до', before, br.dry)
        main = br.restart_leon2(LEON2_MAIN_CTRL)
        sub = br.restart_leon2(LEON2_SUB_CTRL)
        if not br.dry:
            print(f'после STOP/RUN: Main ctrl={main:#010x}, Sub ctrl={sub:#010x}')
        after = br.sample_recovery_state(delay=1.0)
        print_recovery_state('после STOP/RUN', after, br.dry)
    elif args.recover:
        recover_stbc(br)
    else:
        addr, length = args.ahb_read
        data = br.read_ahb(addr, length)
        if args.dry_run:
            return
        if args.out:
            with open(args.out, 'wb') as f:
                f.write(data)
            print(f'{len(data)} байт AHB с {addr:#010x} → {args.out}')
        else:
            print(data.hex(' '))


class RecoveryVerificationUnavailable(RuntimeError):
    """Reset was requested, but USB/UART cannot confirm its outcome."""


def reconnect_for_recovery(br):
    try:
        br.reconnect_after_reset()
    except (IOError, OSError, TimeoutError) as error:
        raise RecoveryVerificationUnavailable(
            'Команда сброса отправлена, но U7005 не вернулся для проверки. '
            'Это не доказывает отказ загрузки: после возврата в Power Off '
            'мост может быть выключен. Проверьте boot UART или включите монитор '
            'обычной кнопкой; повторный reset автоматически не выполняется. '
            f'Причина недоступности проверки: {error}'
        ) from error


def recover_bootloader_watchdog(br):
    """Reset from the known libre recovery states; never write flash.

    F0E0=55 starts a ~6-second watchdog (captures/watchdog-2026-09-03).
    Unlike F1D, this path does not fabricate a Share Structure or launch an
    image against empty boot parameters. Confirmed by the owner's boot UART
    on 2026-09-13, followed by stock CMD_SYS_POWEROFF and both Leon2 STOP.
    """
    shared = bytes(br.read_reg(0x3000 + i) for i in range(0x9A))
    # After the tested ISP erase/program cycle with FF payload, this RAM
    # region reads back FF rather than the zeros left by libre startup.
    # Accept only these observed states, not an arbitrary damaged structure.
    if shared not in (bytes(0x9A), b'\xFF' * 0x9A):
        raise RuntimeError('отказ watchdog reset: Share Structure не нули и не FF')
    jedec = br.jedec()
    ear = br.spi([0xC8], 1)
    if jedec != b'\xc8\x40\x19' or ear != b'\x00':
        raise RuntimeError('отказ watchdog reset: нужен GD25Q256E в банке 0, '
                           f'JEDEC={jedec.hex(" ")}, EAR={ear.hex(" ")}')
    print(f'Пустой F1D, Share Structure={shared[0]:02X}*154 и EAR=0 проверены; '
          'запускаю watchdog F0E0=55, ожидание ~6 с', flush=True)
    br.write_reg(REG_WATCHDOG_F0E0, WATCHDOG_START_OR_RELOAD)
    br.exit()  # restore bridge UART mode before the scaler resets
    time.sleep(7.0)
    reconnect_for_recovery(br)
    for attempt in range(5):
        try:
            reply = br.heartbeat()
            if reply == b'5b00110000\r':
                print('После watchdog ответил UART-транспорт: 5b00110000; '
                      'успешную загрузку подтвердите по экрану или boot UART', flush=True)
                return
        except (IOError, OSError, TimeoutError):
            pass
        if attempt < 4:
            time.sleep(2.0)
    raise RecoveryVerificationUnavailable(
        'Команда watchdog reset отправлена, но нет ожидаемого UART-ответа. '
        'Проверьте boot UART и состояние Power Off; это не доказательство '
        'отказа загрузки. Повторный reset автоматически не выполняется.')


def recover_stbc(br):
    """Recover a completed FW.034 window or the empty libre bootloader state."""
    descriptor = bytes(br.read_reg(STBC_WINDOW + i)
                       for i in range(len(STBC_FW034_DESCRIPTOR)))
    if br.dry:
        print('  dry-run: F1D или watchdog разрешаются только после живой сверки состояния')
        return
    if descriptor == b'\xAA' + bytes(8):
        recover_bootloader_watchdog(br)
        return
    if descriptor != STBC_FW034_DESCRIPTOR:
        raise RuntimeError('отказ перезапускать STBC: F1D0..F1D8 = '
                           f'{descriptor.hex(" ")}, ожидалось '
                           f'{STBC_FW034_DESCRIPTOR.hex(" ")}')
    before = br.sample_recovery_state()
    print_recovery_state('до recovery', before, br.dry)
    print('STBC-окно FW.034 проверено; пуск F1D0=0x87')
    try:
        br.write_reg(STBC_WINDOW, 0x87)
    except (IOError, OSError, TimeoutError) as e:
        # Сброс 8051 может оборвать ответ той самой транзакции, которая его вызвала.
        print(f'ответ на F1D0=87 оборвался при сбросе STBC: {e}')
    time.sleep(3.0)
    reconnect_for_recovery(br)
    try:
        reply = br.heartbeat()
    except (IOError, OSError, TimeoutError) as error:
        raise RecoveryVerificationUnavailable(
            'Команда F1D recovery отправлена, но UART-проверка недоступна. '
            'Проверьте boot UART и состояние Power Off; повторного сброса нет.'
        ) from error
    print('macro_key после recovery (только проверка UART-транспорта):',
          reply.rstrip(b'\r').decode('ascii', errors='backslashreplace'))
    if reply != b'5b00110000\r':
        raise RecoveryVerificationUnavailable(
            f'После команды F1D нет штатного ответа macro_key: {reply!r}; '
            'исход загрузки не подтверждён через UART-транспорт')


def print_recovery_state(label, state, dry):
    if dry:
        return
    main_ctrl, sub_ctrl, tick1, tick2, stbc1, stbc2 = state
    print(f'{label}: Main ctrl={main_ctrl:#010x}, Sub ctrl={sub_ctrl:#010x}; '
          f'Main tick={tick1:#010x}→{tick2:#010x}; '
          f'STBC Timer0={stbc1:#04x}→{stbc2:#04x}')


if __name__ == '__main__':
    main()
