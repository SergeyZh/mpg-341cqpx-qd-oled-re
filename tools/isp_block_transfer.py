#!/usr/bin/env python3
"""Передача одного 4-КиБ блока штатным ISP-протоколом NT68503.

Это низкоуровневый примитив для пишущих инструментов. Он воспроизводит цикл
BD/BC/BF/C0/C1/C2/C3/B5 из живого захвата FW.034. Сам модуль не входит в ISP,
не выбирает слот, не посылает commit A1 и не открывает USB-устройство.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import time


BLOCK_SIZE = 0x1000
REPORT_SIZE = 64


@dataclass(frozen=True)
class Step:
    name: str
    report: bytes
    reply: str | None


def _pad(data: bytes) -> bytes:
    if len(data) > REPORT_SIZE:
        raise ValueError(f"HID report длиннее {REPORT_SIZE}: {len(data)}")
    return data + bytes(REPORT_SIZE - len(data))


def _xor(slave: int, frame: bytes) -> int:
    value = slave
    for byte in frame:
        value ^= byte
    return value


def _framed(sub: int, read_addr: int, write_addr: int, frame: bytes) -> bytes:
    body = bytes([sub, read_addr, 0, write_addr, len(frame)]) + frame
    body += bytes([_xor(write_addr, bytes([len(frame)]) + frame)])
    return _pad(b"\x04" + body)


def _bc(command: bytes) -> Step:
    if len(command) != 2:
        raise ValueError("BC принимает ровно два байта")
    return Step(f"BC {command.hex(' ')}", _pad(b"\x04\xBC\0\0\xB0" + command), "ack")


def block_steps(address: int, block: bytes) -> tuple[Step, ...]:
    """Построить точную последовательность OUT-отчётов для одного блока."""
    if address < 0 or address > 0xFFFFFFFF or address & (BLOCK_SIZE - 1):
        raise ValueError(f"адрес блока должен быть выровнен на 0x1000: {address:#x}")
    if len(block) != BLOCK_SIZE:
        raise ValueError(f"блок должен быть ровно 0x1000 байт, получено {len(block):#x}")

    steps = [
        Step(
            "BD address",
            _pad(b"\x04\xBD\0\0\xB0" + address.to_bytes(4, "big") + b"\x10"),
            "ack",
        ),
        _bc(b"\xFF\xF3"),
        _bc(b"\xE2\x87"),
        _bc(b"\xFF\xD0"),
        Step("BF data[0:58]", _pad(b"\x04\xBF\0\0\xB0\0" + block[:58]), None),
    ]
    offset = 58
    for number in range(67):
        part = block[offset : offset + 60]
        if len(part) != 60:
            raise AssertionError("неполный C0-фрагмент")
        steps.append(
            Step(f"C0 data {number + 1}/67", _pad(b"\x04\xC0\0\0" + part), None)
        )
        offset += 60
    tail = block[offset : offset + 18]
    if len(tail) != 18 or offset + len(tail) != BLOCK_SIZE:
        raise AssertionError("неверное разбиение 58 + 67*60 + 18")
    steps.extend(
        [
            Step("C1 data tail", _pad(b"\x04\xC1\0\0" + tail), "ack"),
            Step(
                "C2 finish",
                _framed(0xC2, 0, 0x6E, bytes.fromhex("b5 f0 0f 6e 91 13 ec")),
                "ack",
            ),
            _bc(b"\xFF\xF2"),
            Step("C3 poll", _pad(bytes.fromhex("04 c3 b1 00 b0 05")), "c3"),
        ]
    )
    # В захвате индекс равен адресу блока, делённому на 0x100. Поэтому обычный
    # шаг адреса 0x1000 даёт шаг индекса 0x10, а пропуск блоков сохраняется.
    base_index = (address >> 8) & 0xFFFF
    for delta in range(0, 16, 2):
        index = (base_index + delta) & 0xFFFF
        steps.append(
            Step(
                f"B5 verify index {index:#06x}",
                _framed(
                    0xB5,
                    0x6F,
                    0x6E,
                    b"\x36" + index.to_bytes(2, "big") + b"\0",
                ),
                "b5",
            )
        )
    steps.append(_bc(b"\xFF\xF2"))
    return tuple(steps)


def _check_reply(step: Step, response: bytes) -> int | None:
    if step.reply == "ack":
        if response[:3] != bytes([0x04, step.report[1], 0x01]):
            raise IOError(
                f"{step.name}: неожиданный ACK {response[:12].hex(' ')}"
            )
        return None
    if step.reply == "c3":
        if response[:5] != bytes.fromhex("04 c3 01 00 b1"):
            raise IOError(f"C3: неожиданный ответ {response[:12].hex(' ')}")
        return response[5]
    if step.reply == "b5":
        if response[:7] != bytes.fromhex("04 b5 01 00 6f 03 c9"):
            raise IOError(f"B5: неожиданный ответ {response[:12].hex(' ')}")
        if response[9] != _xor(0x6F, response[5:9]):
            raise IOError(f"B5: неверный XOR {response[:12].hex(' ')}")
        return int.from_bytes(response[7:9], "big")
    raise AssertionError(f"неизвестный тип ответа {step.reply!r}")


def transfer_block(bridge, address: int, block: bytes) -> tuple[int, ...]:
    """Передать блок через уже открытый и настроенный ``isp_read.Bridge``."""
    steps = block_steps(address, block)
    c3_index = next(i for i, step in enumerate(steps) if step.reply == "c3")
    for step in steps[:c3_index]:
        if step.reply is None:
            if bridge.dry:
                print(f"  → {step.name}: {step.report.hex(' ')}")
            else:
                bridge.dev.write(step.report)
            continue
        response = bridge._xfer(step.report, step.report[1])
        if bridge.dry:
            continue
        _check_reply(step, response)
    return finish_block(bridge, address)


def finish_block(bridge, address: int) -> tuple[int, ...]:
    """Дождаться C3=55 и выполнить B5/заключительный BC без повтора payload."""
    steps = block_steps(address, bytes(BLOCK_SIZE))
    c3_index = next(i for i, step in enumerate(steps) if step.reply == "c3")
    c3 = steps[c3_index]
    status = None
    for attempt in range(100):
        response = bridge._xfer(c3.report, c3.report[1])
        if bridge.dry:
            status = 0x55
        else:
            status = _check_reply(c3, response)
        if status == 0x55:
            break
        if status != 0x00:
            raise IOError(f"C3: неизвестный статус {status:#04x}")
        if attempt == 0:
            print("C3=00, ISP занят; повторяю опрос", flush=True)
        time.sleep(0.1)
    else:
        raise TimeoutError(f"C3 не перешёл 00→55, последний статус={status:#04x}")

    verification = []
    for step in steps[c3_index + 1 :]:
        response = bridge._xfer(step.report, step.report[1])
        if bridge.dry:
            continue
        value = _check_reply(step, response)
        if value is not None:
            verification.append(value)
    return tuple(verification)


def transfer_image(bridge, address: int, image: bytes) -> tuple[tuple[int, ...], ...]:
    """Передать образ блоками, дополнив последний блок байтами ``0xFF``.

    ``bridge`` уже должен находиться в фазе block transfer с проверенно выбранным
    целевым банком. Функция намеренно не выполняет init, commit ``A1`` или reset.
    """
    if address < 0 or address > 0xFFFFFFFF or address & (BLOCK_SIZE - 1):
        raise ValueError(f"адрес образа должен быть выровнен на 0x1000: {address:#x}")
    if not image:
        raise ValueError("пустой образ")
    padded_length = (len(image) + BLOCK_SIZE - 1) & -BLOCK_SIZE
    padded = image + b"\xFF" * (padded_length - len(image))
    results = []
    for offset in range(0, len(padded), BLOCK_SIZE):
        current = address + offset
        if current > 0xFFFFFFFF:
            raise ValueError("образ выходит за 32-битное адресное пространство")
        results.append(
            transfer_block(bridge, current, padded[offset : offset + BLOCK_SIZE])
        )
    return tuple(results)


def verify_capture(capture: Path) -> None:
    """Сверить генератор со всеми циклами штатного обновления FW.034."""
    from usbpcap_hid import collect, packets

    paths = [str(capture)]
    descriptions, _, _, _ = collect(paths)
    targets = {
        key
        for key, description in descriptions.items()
        if (description[0], description[1]) == (0x1462, 0x3FA4)
    }
    groups: list[list[bytes]] = []
    current: list[bytes] | None = None
    for packet in packets(str(capture)):
        data = bytes(packet.payload or b"")
        if (
            (packet.bus, packet.dev) not in targets
            or packet.xfer != 1
            or not data
            or data[0] != 0x04
            or packet.ep & 0x80
        ):
            continue
        if data[1] == 0xBD:
            if current is not None:
                groups.append(current)
            current = []
        if current is not None:
            current.append(data)
    if current is not None:
        groups.append(current)

    matched = 0
    payloads = []
    addresses = []
    for number, actual in enumerate(groups):
        address = int.from_bytes(actual[0][5:9], "big")
        reports = [data for data in actual if data[1] in (0xBF, 0xC0, 0xC1)]
        if [data[1] for data in reports] != [0xBF] + [0xC0] * 67 + [0xC1]:
            raise RuntimeError(f"цикл {number}: неверное разбиение payload")
        block = (
            reports[0][6:64]
            + b"".join(data[4:64] for data in reports[1:-1])
            + reports[-1][4:22]
        )
        expected = list(block_steps(address, block))
        # Финальный commit-пролог заменяет последний BC FF F2 последнего цикла.
        if number == len(groups) - 1:
            expected = expected[:-1]
        position = 0
        for step in expected:
            while position < len(actual) and actual[position] != step.report:
                position += 1
            if position == len(actual):
                raise RuntimeError(
                    f"цикл {number}, адрес {address:#x}: нет шага {step.name}"
                )
            position += 1
            matched += 1
        addresses.append(address)
        payloads.append(block)

    if len(groups) != 618 or len(set(addresses)) != 617:
        raise RuntimeError(
            f"неожиданное число циклов/адресов: {len(groups)}/{len(set(addresses))}"
        )
    repeated = [i for i, address in enumerate(addresses) if address == 0x7000]
    if repeated != [616, 617] or payloads[616] != payloads[617]:
        raise RuntimeError("финальные повторы блока 0x7000 не совпали")
    print(
        f"OK: {len(groups)} циклов, {len(set(addresses))} уникальных адресов, "
        f"{matched} отчётов совпали; 0x7000 передан дважды"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verify-capture",
        type=Path,
        required=True,
        help="офлайн сверить генератор с pcapng штатного обновления",
    )
    args = parser.parse_args()
    verify_capture(args.verify_capture)


if __name__ == "__main__":
    main()
