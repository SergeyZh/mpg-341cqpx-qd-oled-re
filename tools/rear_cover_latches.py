#!/usr/bin/env python3
"""Карта защёлок задней крышки в SVG — для docs/disassembly.md.

Контур монитора перерисован с вида сзади на стр. 10 руководства
пользователя MPG 341CQPX QD-OLED v1.1 с сайта MSI (координаты — в пикселях
этого чертежа при 400 dpi: pdftoppm -f 10 -l 10 -r 400).
Чертёж в масштабе: рамка 1305 px = ширина 812 мм из спецификации руководства.
Верхние защёлки — по замерам владельца на крышке (мм от оси); остальные
перенесены с рукописного эскиза photo/back_cover_latches_sketch.jpeg по
ориентирам: углы крышки, ось, разъём питания, блок разъёмов. Стрелка изображает саму зацепку — её бугорок — и указывает
направление зацепа; две стрелки рядом — сдвоенная зацепка, зубцы через 8 мм.

    .venv/bin/python tools/rear_cover_latches.py -o docs/rear_cover_latches.svg

PNG для документа — снимком headless Chrome (масштаб 2):

    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new \
        --hide-scrollbars --force-device-scale-factor=2 --window-size=1440,1180 \
        --screenshot="$PWD/docs/rear_cover_latches.png" "file://$PWD/docs/rear_cover_latches.svg"
"""
import argparse

OX, OY = 40, 100           # сдвиг чертежа от края листа
W, H = 1440, 1180
INK = '#222'
GHOST = '#9a9a9a'
ON_BODY = '#1f5fbf'        # верх: зацепка на корпусе, в крышке отверстие
ON_COVER = '#d0342c'       # низ, бока, углы: зацепка на самой крышке
L = 42                     # длина стрелки
MM = 1305 / 812            # px на мм
AXIS = 672.5               # ось симметрии: середина рамки
PAIR = 4 * MM              # полуразнос зубцов сдвоенной зацепки (8 мм)

# Верхний край крышки — квадратичная кривая (145,186)…(672,140)…(1200,186).
def top_y(x):
    t = (x - 145) / 1055
    return 186 - 92 * t * (1 - t)

# Верх, замер: центральные пары — 63 мм между внутренними зубцами, дальше
# шаг пар от оси 85, 80, 75 мм; симметрично. Центры пар, мм от оси:
TOP_MM = [31.5 + 4]
for step in (85, 80, 75):
    TOP_MM.append(TOP_MM[-1] + step)
TOP = sorted((AXIS + sign * mm * MM, 2) for mm in TOP_MM for sign in (-1, 1))
# (x, число) — низ снаружи вверх; бока снаружи внутрь; по эскизу
BOTTOM = [(215, 1), (298, 2), (386, 2), (477, 2), (606, 2), (735, 2), (824, 2),
          (1103, 1), (1156, 1)]
SIDE = [(254, 2), (337, 2), (403, 1), (449, 1)]   # одинаково слева и справа
CORNERS = [((116, 194), (1, 1)), ((1226, 195), (-1, 1)),
           ((1222, 518), (-1, -1)), ((120, 518), (1, -1))]


def arrow(tip, d, color):
    n = (d[0] ** 2 + d[1] ** 2) ** 0.5
    ux, uy = d[0] / n, d[1] / n
    tx, ty = tip
    bx, by = tx - ux * 13, ty - uy * 13           # основание наконечника
    px, py = -uy, ux
    head = (f'{tx:.1f},{ty:.1f} {bx + px * 6:.1f},{by + py * 6:.1f} '
            f'{bx - px * 6:.1f},{by - py * 6:.1f}')
    return (f'<line x1="{tx - ux * L:.1f}" y1="{ty - uy * L:.1f}" x2="{bx:.1f}" '
            f'y2="{by:.1f}" stroke="{color}" stroke-width="3.2" stroke-linecap="round"/>'
            f'<polygon points="{head}" fill="{color}"/>')


def group(tip, d, count, color):
    if count == 1:
        return [arrow(tip, d, color)]
    px, py = (0, 1) if d[0] else (1, 0)        # разнос поперёк направления
    return [arrow((tip[0] - px * PAIR, tip[1] - py * PAIR), d, color),
            arrow((tip[0] + px * PAIR, tip[1] + py * PAIR), d, color)]


def latches():
    out = []
    for x, c in TOP:
        if c == 2:   # пара стрелок по кривой: каждая со своей высотой края
            for dx in (-PAIR, PAIR):
                out.append(arrow((x + dx, top_y(x + dx) + 3), (0, -1), ON_BODY))
        else:
            out.append(arrow((x, top_y(x) + 3), (0, -1), ON_BODY))
    for x, c in BOTTOM:
        out += group((x, 528), (0, -1), c, ON_COVER)
    for y, c in SIDE:
        out += group((108, y), (1, 0), c, ON_COVER)
        out += group((1235, y), (-1, 0), c, ON_COVER)
    for tip, d in CORNERS:
        out.append(arrow(tip, d, ON_COVER))
    return out


MONITOR = f'''
<rect x="20" y="15" width="1305" height="583" rx="7" fill="#fbfbfb" stroke="{INK}" stroke-width="2.5"/>
<path d="M22,482 L110,450 M40,484 L40,596 M22,484 L40,484" fill="none" stroke="{INK}" stroke-width="1.6"/>
<path d="M1235,450 L1322,478 M1302,478 L1302,596 M1302,478 L1322,478" fill="none" stroke="{INK}" stroke-width="1.6"/>
<path d="M145,186 Q672,140 1200,186 Q1232,190 1233,222 L1230,495 Q1228,522 1195,525 L150,525
         Q114,522 112,495 L110,222 Q110,188 145,186 Z" fill="#f1f1f1" stroke="{INK}" stroke-width="2.6"/>
<path d="M150,210 Q672,166 1193,210 Q1222,212 1222,240 L1221,492 Q1220,514 1190,516 L155,516
         Q121,514 120,492 L119,240 Q119,212 150,210 Z" fill="none" stroke="{INK}" stroke-width="1.1"/>
<path d="M150,203 Q672,159 1195,203" fill="none" stroke="{INK}" stroke-width="6" stroke-dasharray="5 3"/>
<path d="M150,203 Q672,159 1195,203" fill="none" stroke="#f1f1f1" stroke-width="3" stroke-dasharray="5 3"/>
<path d="M265,529 L610,529 M735,529 L850,529" fill="none" stroke="{INK}" stroke-width="6" stroke-dasharray="5 3"/>
<path d="M265,529 L610,529 M735,529 L850,529" fill="none" stroke="#fbfbfb" stroke-width="3" stroke-dasharray="5 3"/>
<path d="M245,532 L215,590 M283,525 L283,596 M490,525 L490,596" fill="none" stroke="{INK}" stroke-width="1.6"/>
<path d="M1085,532 L1128,592 L1300,592" fill="none" stroke="{INK}" stroke-width="1.6"/>
<rect x="398" y="525" width="64" height="22" rx="2" fill="#fff" stroke="{INK}" stroke-width="2"/>
<path d="M420,537 q5,-6 10,0 t10,0" fill="none" stroke="{INK}" stroke-width="1.6"/>
<rect x="850" y="525" width="233" height="20" fill="#fff" stroke="{INK}" stroke-width="2"/>
<rect x="1062" y="525" width="21" height="20" fill="#fff" stroke="{INK}" stroke-width="1.6"/>
<rect x="1219" y="554" width="12" height="7" rx="3" fill="none" stroke="{INK}" stroke-width="1.6"/>
<rect x="1220" y="568" width="10" height="8" fill="none" stroke="{INK}" stroke-width="1.6"/>
<path d="M1222,568 v-3 a3,3 0 0 1 6,0 v3" fill="none" stroke="{INK}" stroke-width="1.6"/>
<rect x="570" y="262" width="203" height="196" rx="7" fill="#e9e9e9" stroke="{INK}" stroke-width="2"/>
<path d="M655,196 L655,265 M663,196 L663,265 M680,196 L680,265 M690,196 L690,265" stroke="{INK}" stroke-width="1.6"/>
'''

STAND = f'''
<g fill="none" stroke="{GHOST}" stroke-width="2" stroke-dasharray="7 5">
<path d="M622,300 Q620,270 672,268 Q725,270 724,300 L740,812 L605,812 Z"/>
<path d="M650,300 L660,780 M700,300 L690,780"/>
<path d="M625,812 L625,835 L718,835 L718,812"/>
<path d="M600,822 L165,850 L170,860 L560,845 M745,822 L1180,850 L1175,860 L790,845"/>
<path d="M552,822 Q575,812 600,822 L598,855 L556,858 Z M745,822 Q770,812 793,822 L790,858 L748,855 Z"/>
</g>
'''


def labels():
    t = []
    def text(x, y, s, size=20, anchor='middle', weight='normal', color=INK):
        t.append(f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}" '
                 f'font-weight="{weight}" fill="{color}">{s}</text>')
    def lead(x1, y1, x2, y2):
        t.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{INK}" stroke-width="1.2"/>')
    t.append(f'<line x1="672" y1="120" x2="672" y2="640" stroke="{GHOST}" stroke-width="1.4" '
             f'stroke-dasharray="18 6 3 6"/>')
    text(672, 112, 'ось', 17, color='#666')
    lead(430, 547, 430, 618); text(430, 640, 'питание 230 В', 19)
    lead(966, 545, 966, 618); text(966, 640, 'HDMI · HDMI · DP · USB-C · USB-A · USB-B · наушники', 19)
    lead(1225, 578, 1225, 650); text(1225, 672, 'замок Kensington', 19)
    text(672, 760, 'подставка (контуром)', 17, color='#888')
    text(1100, 300, 'задняя крышка', 22, color='#777')
    text(1100, 326, '(вид сзади)', 18, color='#777')
    text(20, -58, 'MSI MPG 341CQPX QD-OLED — защёлки задней крышки', 30, 'start', 'bold')
    text(20, -26, 'Вид сзади: левый край рисунка — правый край экрана, если смотреть спереди. '
         'Масштаб по ширине 812 мм.', 18, 'start', color='#444')
    return t


def legend():
    y = OY + 930
    g = [f'<g transform="translate(60,{y})">']
    g.append(arrow((20, -14), (0, -1), ON_BODY))
    g.append(f'<text x="48" y="14" font-size="19" fill="{INK}">верхний край: зацепка на корпусе '
             f'монитора, в крышке отверстие — 8 пар, 16 шт.; положения измерены</text>')
    g.append(arrow((20, 40), (0, -1), ON_COVER))
    g.append(f'<text x="48" y="68" font-size="19" fill="{INK}">низ, бока и углы: зацепка на самой '
             f'крышке — низ 15, бока по 6, углы 4; положения по эскизу</text>')
    g.append(f'<text x="48" y="118" font-size="19" font-weight="bold" fill="{INK}">'
             f'Всего 47 защёлок. Стрелка — бугорок зацепки и направление зацепа; двойная — зубцы через 8 мм.</text>')
    g.append('</g>')
    return g


def main():
    ap = argparse.ArgumentParser(description='Карта защёлок задней крышки в SVG')
    ap.add_argument('-o', '--output', required=True)
    args = ap.parse_args()
    body = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
            f'viewBox="0 0 {W} {H}" font-family="Helvetica, Arial, sans-serif">',
            f'<rect width="{W}" height="{H}" fill="#fff"/>',
            f'<g transform="translate({OX},{OY})">', MONITOR, STAND, *labels(), *latches(), '</g>',
            *legend(), '</svg>']
    with open(args.output, 'w') as f:
        f.write('\n'.join(body) + '\n')


if __name__ == '__main__':
    main()
