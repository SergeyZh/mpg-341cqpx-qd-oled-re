"""Эталоны MSI для проверок U7005 без дампа и без исходного захвата.

aprom() — байты APROM MSI 5.4, нужные проверкам: из полного дампа
(`U7005_REFERENCE`) или из tests/data/msi-aprom.txt. Чтение вне записанных
диапазонов — ошибка, а не нули.

update_packets() — HID-отчёты 4 штатного обновления FW.034 в исходном порядке.
tests/data/update-034.txt хранит их текстом: байты, которых нет в файле FW.034,
записаны явно, страницы прошивки — ссылками на смещения в файле, который
читатель скачивает у MSI (`U7005_FW034`). Результат сверяется с SHA-256,
посчитанным по исходному захвату.
"""
import hashlib
import os
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parents[1]
DATA = PROJECT/'tests/data'
FW034_SHA256 = 'a3c033105dc044fcf7f560cdb03145c8a4ef64c6220f44bab1bebf1cb3a1965d'
PAGE_FAMILY = (0xbf, 0xc0, 0xc1)


def parse_ranges(text):
    """Строки «адрес: байты» → {адрес: байт}; адрес шестнадцатеричный."""
    patch = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        address, _, data = line.partition(':')
        for offset, value in enumerate(bytes.fromhex(data)):
            patch[int(address, 16) + offset] = value
    return patch


class Sparse:
    def __init__(self, patch):
        self.patch = patch

    def __getitem__(self, item):
        missing = [a for a in range(item.start, item.stop) if a not in self.patch]
        if missing:
            raise KeyError(f'APROM {missing[0]:#x}: нет в эталоне {DATA/"msi-aprom.txt"}')
        return bytes(self.patch[a] for a in range(item.start, item.stop))


def aprom():
    path = os.environ.get('U7005_REFERENCE')
    if path:
        return Path(path).read_bytes()
    return Sparse(parse_ranges((DATA/'msi-aprom.txt').read_text()))


def fw034():
    path = Path(os.environ.get('U7005_FW034', ROOT/'MSI_MPG_341CQPX_QD-OLED_FW.034_D728.bin'))
    data = path.read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    assert actual == FW034_SHA256, f'{path}: SHA-256 {actual}, нужен файл FW.034 MSI'
    return data


def packets_sha256(packets):
    digest = hashlib.sha256()
    for out, payload in packets:
        digest.update((b'>' if out else b'<') + payload)
    return digest.hexdigest()


def _encode_payload(payload, firmware, cursor, pages):
    """Токены: hex-литерал, `XX*N` — повтор байта, `@X` — курсор в FW.034, `=N` — копия."""
    tokens, literal, body, i = [payload[:4].hex()], bytearray(), payload[4:], 0

    def flush():
        if literal:
            tokens.append(literal.hex())
            literal.clear()

    def match(at):
        k = 0
        while i + k < len(body) and at + k < len(firmware) and body[i + k] == firmware[at + k]:
            k += 1
        return k

    while i < len(body):
        k = match(cursor) if pages and cursor is not None else 0
        if k >= 8:
            flush()
            tokens.append(f'={k}')
            cursor, i = cursor + k, i + k
            continue
        run = 1
        while i + run < len(body) and body[i + run] == body[i]:
            run += 1
        if run >= 4:
            flush()
            tokens.append(f'{body[i]:02x}*{run}')
            i += run
            continue
        found = firmware.find(body[i:i + 16]) if pages and len(body) - i >= 16 else -1
        if found >= 0:
            k = match(found)
            flush()
            tokens += [f'@{found:x}', f'={k}']
            cursor, i = found + k, i + k
            continue
        literal.append(body[i])
        i += 1
    flush()
    return ' '.join(tokens), cursor


def encode_update(packets, firmware):
    lines, cursor = [], None
    for out, payload in packets:
        assert len(payload) == 64
        text, cursor = _encode_payload(payload, firmware, cursor, payload[1] in PAGE_FAMILY)
        line = ('> ' if out else '< ') + text
        if lines and lines[-1][0] == line:
            lines[-1][1] += 1
        else:
            lines.append([line, 1])
    return [line if n == 1 else f'{line} x{n}' for line, n in lines]


def decode_update(text, firmware):
    packets, cursor, expected = [], None, None
    for line in text.splitlines():
        if line.startswith('packets-sha256:'):
            expected = line.split()[1]
        if not line or line[0] not in '<>':
            continue
        out, tokens = line[0] == '>', line[2:].split()
        repeat = int(tokens.pop()[1:]) if tokens[-1].startswith('x') else 1
        for _ in range(repeat):
            payload = bytearray()
            for token in tokens:
                if token[0] == '@':
                    cursor = int(token[1:], 16)
                elif token[0] == '=':
                    n = int(token[1:])
                    assert cursor + n <= len(firmware)
                    payload += firmware[cursor:cursor + n]
                    cursor += n
                elif '*' in token:
                    value, count = token.split('*')
                    payload += bytes([int(value, 16)]) * int(count)
                else:
                    payload += bytes.fromhex(token)
            assert len(payload) == 64, line
            packets.append((out, bytes(payload)))
    assert expected and packets_sha256(packets) == expected, 'эталон обновления не совпал с захватом'
    return packets


def update_packets():
    return decode_update((DATA/'update-034.txt').read_text(), fw034())
