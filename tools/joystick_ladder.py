#!/usr/bin/env python3
"""Схема резистивной лестницы джойстика в PNG — для docs/buttons.md и статей.

Коды АЦП и линии CN4002 — из docs/buttons.md и docs/hardware-boards.md. Номиналы
резисторов и топология не прозвонены: схема показывает параллельный вариант, а
подписи — только отношения Rk/Rpu = код / (255 − код), которые следуют из кодов.

    .venv/bin/python tools/joystick_ladder.py -o docs/joystick_ladder.png
"""
import argparse

from PIL import Image, ImageDraw, ImageFont

S = 2                      # масштаб: рисуем в логических точках, сохраняем вдвое крупнее
W, H = 1240, 960
FONT = '/System/Library/Fonts/Supplemental/Arial.ttf'
BOLD = '/System/Library/Fonts/Supplemental/Arial Bold.ttf'
MONO = '/System/Library/Fonts/Menlo.ttc'

INK = (30, 30, 30)
WIRE = (40, 40, 40)
GREY = (120, 120, 120)
ACCENT = (190, 60, 40)     # измеренные значения
BOARD = (235, 241, 248)

# (подпись, код АЦП, напряжение измерено мультиметром) — docs/buttons.md, таблица декодера
KEYS = [('вправо', 0x3B, True), ('влево', 0x74, False), ('вниз', 0xA2, False),
        ('вверх', 0xCA, True), ('нажатие', 0x00, False)]
VREF = 3.3


def font(path, size):
    return ImageFont.truetype(path, size * S)


def main():
    ap = argparse.ArgumentParser(description='Схема лестницы джойстика в PNG')
    ap.add_argument('-o', '--output', required=True)
    args = ap.parse_args()

    img = Image.new('RGB', (W * S, H * S), 'white')
    d = ImageDraw.Draw(img)
    f13, f15 = font(FONT, 13), font(FONT, 15)
    b15, b22 = font(BOLD, 15), font(BOLD, 22)
    m13, m14 = font(MONO, 13), font(MONO, 14)

    def p(*xy):
        return [v * S for v in xy]

    def line(*xy, w=2, fill=WIRE):
        d.line(p(*xy), fill=fill, width=w * S)

    def text(x, y, s, f=f15, fill=INK, anchor='la'):
        d.text((x * S, y * S), s, font=f, fill=fill, anchor=anchor)

    def dashed(x0, y0, x1, y1, step=8):
        """Горизонтальная или вертикальная пунктирная линия."""
        n = int(max(abs(x1 - x0), abs(y1 - y0)) // step)
        for i in range(0, n, 2):
            line(x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n,
                 x0 + (x1 - x0) * (i + 1) / n, y0 + (y1 - y0) * (i + 1) / n)

    def dot(x, y):
        d.ellipse(p(x - 5, y - 5, x + 5, y + 5), fill=WIRE)

    def resistor(x, y0, y1):
        """Вертикальный резистор (обозначение ГОСТ/IEC) между y0 и y1."""
        m = (y0 + y1) / 2
        line(x, y0, x, m - 32)
        d.rectangle(p(x - 11, m - 32, x + 11, m + 32), outline=WIRE, width=2 * S, fill='white')
        line(x, m + 32, x, y1)

    def switch(x, y0, y1):
        """Нормально разомкнутая кнопка между y0 и y1."""
        a, b = (y0 + y1) / 2 - 22, (y0 + y1) / 2 + 22
        line(x, y0, x, a)
        line(x, b, x, y1)
        d.ellipse(p(x - 4, a - 4, x + 4, a + 4), outline=WIRE, width=2 * S, fill='white')
        d.ellipse(p(x - 4, b - 4, x + 4, b + 4), outline=WIRE, width=2 * S, fill='white')
        line(x, b - 4, x - 20, a + 2)

    def ground(x, y):
        line(x, y, x, y + 14)
        for i, half in enumerate((16, 10, 4)):
            line(x - half, y + 14 + i * 6, x + half, y + 14 + i * 6)

    text(40, 30, 'Джойстик MSI MPG 341CQPX QD-OLED: резистивная лестница на АЦП', b22)
    text(40, 62, 'Пять положений джойстика дают пять уровней на одной линии АЦП скалера NT68503', f15, GREY)

    # Плата Main и скалер
    d.rounded_rectangle(p(24, 100, 640, 690), radius=10 * S, outline=GREY, width=1 * S, fill=BOARD)
    text(40, 112, 'Main PCB', b15, GREY)
    d.rectangle(p(60, 230, 290, 440), outline=INK, width=2 * S, fill='white')
    text(175, 248, 'NT68503', b15, anchor='ma')
    text(278, 300, 'ADC5', b15, anchor='rm')
    text(278, 390, 'GPIO1.0', b15, anchor='rm')
    text(76, 322, 'Main:  0xCF03CF24', m13, GREY)
    text(76, 340, 'STBC:  XDATA F3C9', m13, GREY)
    text(76, 358, '8 бит, 0…3,3 В', f13, GREY)
    text(76, 412, 'порог ≈ 1 В (цифровой)', f13, GREY)

    node_x, node_y = 440, 300
    # Подтяжка к +3,3 В
    line(node_x - 30, 150, node_x + 30, 150)
    text(node_x, 140, '+3,3 В', b15, anchor='md')
    resistor(node_x, 150, node_y)
    text(node_x + 20, 225, 'Rpu', b15, anchor='lm')
    text(node_x + 20, 245, 'номинал и плата', f13, GREY, 'lm')
    text(node_x + 20, 261, 'не прозвонены', f13, GREY, 'lm')
    # Скалер → узел
    line(290, node_y, 640, node_y)
    dot(node_x, node_y)
    # GPIO1.0 повторяет уровень линии (вправо и нажатие → 0), но общий ли это вывод — вывод
    dashed(290, 390, 380, 390)
    dashed(380, 390, 380, node_y)
    text(392, 390, 'вероятно, тот же', f13, GREY, 'lm')
    text(392, 406, 'вывод (не прозвонено)', f13, GREY, 'lm')
    dot(380, node_y)
    text(node_x + 10, node_y - 10, 'покой: 0xFF · 3,3 В', m13, GREY, 'ld')
    # Земля скалера
    gnd_y = 600
    line(520, gnd_y, 640, gnd_y)
    line(520, gnd_y, 520, gnd_y + 10)
    ground(520, gnd_y + 10)

    # Разъём CN4002
    d.rectangle(p(640, 260, 680, 640), outline=INK, width=2 * S, fill='white')
    text(660, 252, 'CN4002', b15, anchor='md')
    text(660, node_y, '1', b15, anchor='mm')
    text(660, gnd_y, '2', b15, anchor='mm')

    # Плата джойстика
    d.rounded_rectangle(p(700, 100, 1216, 690), radius=10 * S, outline=GREY, width=1 * S, fill=BOARD)
    text(716, 112, 'плата джойстика', b15, GREY)
    xs = [770, 860, 950, 1040, 1130]
    line(680, node_y, xs[-1], node_y)
    line(680, gnd_y, xs[-1], gnd_y)
    for i, (name, code, measured) in enumerate(KEYS):
        x = xs[i]
        if i < len(xs) - 1:
            dot(x, node_y)
            dot(x, gnd_y)
        if code:
            resistor(x, node_y, 440)
            text(x + 16, 370, f'R{i + 1}', b15, anchor='lm')
            switch(x, 440, gnd_y)
        else:
            switch(x, node_y, gnd_y)
        text(x, 630, name, b15, anchor='ma')
        volts = code / 255 * VREF
        text(x, 652, f'0x{code:02X}', m14, ACCENT if measured else INK, 'ma')
        text(x, 670, f'{volts:.2f} В'.replace('.', ','), f13, ACCENT if measured else INK, 'ma')

    # Таблица
    ty = 720
    text(40, ty, 'Делитель: V = 3,3 · Rk / (Rpu + Rk), отсюда Rk / Rpu = код / (255 − код)', b15)
    cols = [40, 190, 300, 420, 540, 760]
    heads = ['положение', 'код АЦП', 'уровень', 'Rk / Rpu', 'окно декодера', 'маска']
    for x, h in zip(cols, heads):
        text(x, ty + 34, h, b15, GREY)
    windows = {0x3B: '0x25–0x51', 0x74: '0x60–0x84', 0xA2: '0x93–0xAF',
               0xCA: '0xBD–0xD3', 0x00: '0x00–0x1E'}
    masks = {0x3B: '0x04', 0x74: '0x08', 0xA2: '0x10', 0xCA: '0x20', 0x00: '0x02'}
    rows = [('покой', 0xFF, False)] + KEYS
    for r, (name, code, measured) in enumerate(rows):
        y = ty + 60 + r * 22
        ratio = '∞' if code == 0xFF else f'{code / (255 - code):.2f}'.replace('.', ',')
        volts = f'{code / 255 * VREF:.2f} В'.replace('.', ',') + (' изм.' if measured else '')
        cells = [name, f'0x{code:02X}', volts, ratio, windows.get(code, 'вне окон'), masks.get(code, '0x00')]
        for x, c in zip(cols, cells):
            text(x, y, c, m14 if c.startswith(('0x', '∞')) or c[0].isdigit() else f15,
                 ACCENT if (measured and x == cols[2]) else INK)

    text(40, H - 36, 'Красным — напряжения, измеренные мультиметром на CN4002 pin 1 (2026-09-13); '
         'коды АЦП прочитаны с живого скалера.', f13, GREY)
    text(40, H - 18, 'Топология не прозвонена: те же уровни даёт и последовательная цепочка. '
         'Достоверны только отношения Rk / Rpu.', f13, GREY)

    img.save(args.output, optimize=True)
    print(f'{args.output}: {img.width}×{img.height}')


if __name__ == '__main__':
    main()
