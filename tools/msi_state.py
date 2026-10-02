#!/usr/bin/env python3
"""Read-only снимок состояния монитора: USB-ветка и все GET-параметры.

Нужен там, где надо сравнить «до» и «после» какого-то воздействия — нажатия
внутренней кнопки `SW4101`, входа в сервисный режим, сброса настроек. Смысл
инструмента именно в сравнимости: снимки «до» и «после» обязаны быть сняты
**одним и тем же кодом**, иначе в диффе будет форматирование, а не состояние.

Что делает:

* перечисляет USB-устройства через `ioreg -p IOUSB -l` с их `vid:pid`. Здесь
  видно и хаб монитора, и всё, что за ним; появление `0603:1234` означало бы
  вход в ISP-тракт `stbc-aux` (`docs/usb-isp.md`);
* опрашивает монитор запросами `58<id>` отчётом `0x01` через мост `U7005`
  (`docs/usb-hid-msi.md`). Список идентификаторов берётся из таблицы в
  `docs/msi-uart-settings-protocol.md`, а не набирается руками;
* печатает значение и текстом, и в hex: часть ответов содержит небуквенные
  байты, которые при декоде теряются (так `00140` = `30 30 A5` выглядит как
  `00?`).

**Только чтение.** Шлются исключительно запросы `58…`. Три идентификатора
пропущены намеренно: `001f` и `00650` — write-only, `00840` — `reset`; читать
их бессмысленно, а риск ненулевой. Монитор в ISP не вводится и не выводится.

    .venv/bin/python tools/msi_state.py                       # на экран
    .venv/bin/python tools/msi_state.py -o out/after.txt --label "после нажатия"
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys
import time


DOC = Path(__file__).resolve().parent.parent / "docs" / "msi-uart-settings-protocol.md"
VID, PID = 0x1462, 0x3FA4
SKIP = {"001f", "00650", "00840"}       # write-only и reset — не трогаем
EXTRA = ["00140", "00150"]              # модель и версия, лежат в другой таблице
MONITOR_VIDS = (0x1462, 0x0603)


def setting_ids() -> list[str]:
    """Идентификаторы из таблиц документа, в порядке появления."""
    ids: list[str] = []
    for line in DOC.read_text().splitlines():
        match = re.match(r"^\|\s*`([0-9a-f:;<=>]{4,5})`\s*\|", line)
        if match and match.group(1) not in ids:
            ids.append(match.group(1))
    if not ids:
        raise SystemExit(f"не нашёл ни одного идентификатора в {DOC}")
    return EXTRA + [i for i in ids if i not in SKIP and i not in EXTRA]


def usb_tree() -> list[str]:
    """Дерево USB-устройств с vid:pid; отступ повторяет вложенность."""
    try:
        raw = subprocess.run(["ioreg", "-p", "IOUSB", "-l", "-w0"],
                             capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError) as error:
        return [f"  (ioreg недоступен: {error})"]
    rows: list[list] = []
    node = None
    for line in raw.splitlines():
        match = re.search(r"\+-o (.+?)@([0-9a-f]+)\s+<class IOUSBHostDevice", line)
        if match:
            depth = (len(line) - len(line.lstrip(" |"))) // 2
            node = [depth, match.group(1), match.group(2), "????", "????"]
            rows.append(node)
        if node:
            for key, index in (("idVendor", 3), ("idProduct", 4)):
                value = re.search(rf'"{key}" = (\d+)', line)
                if value:
                    node[index] = f"{int(value.group(1)):04x}"
    return [f"  {'  ' * d}{vid}:{pid}  {name} @{port}"
            for d, name, port, vid, pid in rows]


def hid_interfaces(hid) -> list[str]:
    out = []
    for device in sorted(hid.enumerate(), key=lambda x: (x["vendor_id"], x["product_id"])):
        if device["vendor_id"] in MONITOR_VIDS:
            out.append(f"  {device['vendor_id']:04x}:{device['product_id']:04x}  "
                       f"{device.get('product_string') or ''} "
                       f"/ sn={device.get('serial_number') or ''}")
    return out or ["  (устройств монитора не найдено)"]


def ask(device, command: str) -> bytes | None:
    device.write(bytes([0x01]) + command.encode() + b"\r" + bytes(63 - len(command)))
    for _ in range(12):
        reply = bytes(device.read(64, timeout_ms=400))
        if reply and reply[0] == 0x01 and b"\r" in reply[1:]:
            return reply[1:reply.index(b"\r", 1)]
    return None


def snapshot(label: str) -> str:
    try:
        import hid
    except ImportError:
        raise SystemExit("нужен модуль hid: .venv/bin/pip install hidapi")

    ids = setting_ids()
    out = [f"# Снимок состояния монитора — {label}", ""]
    out.append("== USB: устройства (ioreg -p IOUSB), vid:pid ==")
    out += usb_tree()
    out.append("")
    out.append("== USB: HID-интерфейсы монитора ==")
    out += hid_interfaces(hid)
    out.append("")

    if not hid.enumerate(VID, PID):
        raise SystemExit(f"устройство {VID:04x}:{PID:04x} (U7005) не найдено")
    device = hid.device()
    device.open(VID, PID)
    device.set_nonblocking(0)
    out.append(f"== GET-параметры, {len(ids)} штук: id, значение текстом, значение в hex ==")
    answered = 0
    try:
        for identifier in ids:
            body = ask(device, "58" + identifier)
            tag = f"5b{identifier}".encode()
            if body is None:
                out.append(f"  {identifier}  <нет ответа>")
            elif body.startswith(tag):
                answered += 1
                value = body[len(tag):]
                out.append(f"  {identifier}  {value.decode('ascii', 'replace'):<16} "
                           f"{value.hex(' ')}")
            else:
                out.append(f"  {identifier}  <иной тег: "
                           f"{body.decode('ascii', 'replace')} | {body.hex(' ')}>")
            time.sleep(0.08)
    finally:
        device.close()
    out.append("")
    out.append(f"ответили штатно: {answered} из {len(ids)}")
    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-o", "--output", type=Path,
                        help="куда записать снимок; без ключа только на экран")
    parser.add_argument("--label", default="без метки",
                        help="метка в заголовке снимка")
    args = parser.parse_args()
    text = snapshot(args.label)
    sys.stdout.write(text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)


if __name__ == "__main__":
    main()
