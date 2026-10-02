# Скалеры в OLED-мониторах MSI

Дата исследования: 2026-08-17.

## Краткий вывод

В актуальной игровой QD-OLED-линейке MSI нет единой scaler-платформы. По
официальным прошивкам обнаружены три производителя:

| Производитель | Текущие модели | С legacy MEG 342C |
|---|---:|---:|
| Realtek | 16 | 16 |
| Novatek | 13 | 14 |
| MStar / MediaTek | 1 | 1 |

Точные семейства, найденные внутри firmware:

- Novatek: `NT68497`, `NT68501`, `NT68503`, `NT68550`, `NT68551`, `NT68553`;
- Realtek: `RTD2711`, `RTD2721`, `RTD2737`, `RTD2738`, `RTD2739`;
- MStar/MediaTek: `MST9U6`.

Название серии не определяет платформу. Например:

- `MPG 341CQPX` использует firmware target Novatek `NT68503`;
- `MPG 341CQR X36` — Realtek `RTD2739`;
- `MAG 341CQP` — Novatek `NT68503`;
- `MAG 341CQP X28` — Realtek `RTD2711`.

У одной retail-модели могут существовать аппаратные ветки с разными
скалерами: у `MAG 271QPX QD-OLED` firmware `0XX/1XX` предназначены для
`NT68551`, а `2XX/3XX` — для `NT68553`.

## Охват

Исходный каталог — официальная страница
[MSI QD-OLED Gaming Monitors](https://www.msi.com/Landing/best-qd-oled-gaming-monitor-display).
Проверены:

- 30 моделей актуальной игровой линейки;
- legacy `MEG 342C QD-OLED`;
- 31 официальный ZIP;
- 37 scaler firmware BIN: несколько SKU имеют параллельные аппаратные ветки.

Для каждого SKU запрашивался официальный endpoint:

```text
https://www.msi.com/api/v1/product/support/panel?product=<slug>&type=firmware
```

Пример: [MPG 341CQPX firmware API](https://www.msi.com/api/v1/product/support/panel?product=MPG-341CQPX-QD-OLED&type=firmware).

В исследование включены только записи `Scaler Firmware` / `Scaler - Firmware`.
Исключены updater, installation guide как самостоятельный payload, MCU, Type-C и
USB-hub firmware. PDF с правилами выбора аппаратной firmware-ветки сохранены как
сопроводительные материалы.

## Метод идентификации

1. Скачать ZIP с `download.msi.com`.
2. Сверить SHA-256 архива с полем MSI support API.
3. Извлечь все scaler BIN, не объединяя разные firmware branches.
4. Для Novatek запустить:

   ```bash
   .venv/bin/python tools/fwmap.py FW.bin
   ```

   и проверить таблицу разделов, блоки `55 AA 66 99`, особенно
   `SCALER=<model>`, а также строки семейства `NT68500`.
5. Просканировать ASCII и UTF-16LE на `NTxxxxx`, `RTDxxxx`, `MSTxxxx`,
   `Novatek`, `Realtek`, `MStar`, `MediaTek`, `SCALER`, `PANEL`.
6. Принимать строку за идентификатор только при наличии контекста модели
   монитора, панели, version block или build target.
7. Отбрасывать ложные признаки:
   - `Novatek NT68400 Billboard DEV` — USB Billboard, не основной скалер;
   - `MST2SST` / `SST2MST` — термины DisplayPort topology, не MStar;
   - `Flash.dat` в updater — таблица поддерживаемых SPI flash, не firmware
     монитора;
   - случайная разметка `fwmap.py` на Realtek/MStar — неподдерживаемый формат.

Все 31 ZIP прошли проверку MSI SHA-256. Дополнительно вручную перепроверены
характерные сигнатуры всех трёх платформ и нескольких Novatek SKU.

## Классы доказательств

| Код | Значение |
|---|---|
| `CFG` | Структурированный Novatek-блок `SCALER=<model>` — наиболее сильное firmware-доказательство |
| `ID` | Точная модель в version/product/service identity внутри firmware |
| `RTD` | Точный Realtek ID рядом с именами монитора и панели, часто повторённый |
| `BUILD` | Модель MStar в build header, security target и путях исходников |

Уверенность относится к firmware target. Без маркировки корпуса или silicon-ID
она не является абсолютным подтверждением физической ревизии микросхемы.

## Novatek

| Монитор | Проверенная firmware MSI | Скалер | Признак |
|---|---|---|---|
| MAG 271QPX QD-OLED | [FW.040/115/214/303](https://download.msi.com/archive/frm_exe/monitor/MAG_271QPX_QD-OLED_Firmware_v040_v115_v214_v303.zip), 2026-07-15 | `NT68551` для 0XX/1XX; `NT68553` для 2XX/3XX | CFG |
| MAG 272QP QD-OLED X50 | [FW.015](https://download.msi.com/archive/frm_exe/monitor/MAG272QP_X50_v015_7A99.zip), 2026-07-21 | `NT68550` | ID |
| MAG 272QPW QD-OLED X28 | [FW.013](https://download.msi.com/archive/frm_exe/monitor/MAG272QPW_X28_v013_3173.zip), 2026-07-21 | `NT68497` | ID |
| MAG 272UP QD-OLED X24 | [FW.013](https://download.msi.com/archive/frm_exe/monitor/MAG272UP_X24_v013_6BB6.zip), 2026-07-21 | `NT68550` | ID |
| MAG 321UPX QD-OLED | [FW.033/118](https://download.msi.com/archive/frm_exe/monitor/MAG_321UPX_QD-OLED_Firmware_v033_v118.zip), 2026-07-15 | `NT68550` | CFG |
| MAG 322UP QD-OLED E16 | [FW.012](https://download.msi.com/archive/frm_exe/monitor/MAG322UP_E16_v012_1036.zip), 2026-07-21 | `NT68497` | ID, средняя уверенность |
| MAG 341CQP QD-OLED | [FW.041](https://download.msi.com/archive/frm_exe/monitor/MSI_MAG_341CQP_QD-OLED_FW.041_A019.zip), 2025-12-08 | `NT68503` | ID |
| MEG 342C QD-OLED, legacy | [FW.046](https://download.msi.com/archive/frm_exe/monitor/MEG-342C-QD-OLED-FW.046-A841.zip), 2025-11-26 | `NT68501` | ID |
| MPG 321CURX QD-OLED | [FW.025/112](https://download.msi.com/archive/frm_exe/monitor/MPG-321CURX-QD-OLED-v025-v112.zip), 2026-06-01 | `NT68550` | CFG |
| MPG 321URX QD-OLED | [FW.021](https://download.msi.com/archive/frm_exe/monitor/MSI_MPG321URX_V021_7F69.zip), 2026-03-04 | `NT68550` | CFG |
| MPG 321URXW QD-OLED | [FW.013](https://download.msi.com/archive/frm_exe/monitor/MSI_MPG321URXW_V013_8053.zip), 2026-03-04 | `NT68550` | CFG |
| MPG 341CQPX QD-OLED | [FW.037](https://download.msi.com/archive/frm_exe/monitor/MPG-341CQPX-QD-OLED-FW.037-0225.zip), 2026-06-01 | `NT68503` | CFG |
| MPG 491CQP QD-OLED | [FW.030](https://download.msi.com/archive/frm_exe/monitor/MPG-491CQP-QD-OLED-FW.030-7710.zip), 2026-06-01 | `NT68503` | CFG |
| MPG 491CQPX QD-OLED | [FW.023](https://download.msi.com/archive/frm_exe/monitor/MPG-491CQPX-QD-OLED-FW.023-BA47.zip), 2026-06-01 | `NT68550` | CFG |

### Примеры Novatek-доказательств

- `MPG 341CQPX FW.037`: `SCALER=NT68503` на `0x203C28`;
- `MPG 321URX FW.021`: `SCALER=NT68550` на `0x207D68`;
- `MAG 271QPX FW.040`: `SCALER=NT68551` на `0x2038B0`;
- `MAG 271QPX FW.214`: `SCALER=NT68553` на `0x2056A0`;
- `MPG 491CQP FW.030`: `SCALER=NT68503` на `0x2017A8`.

Для исследуемого в этом репозитории `MPG 341CQPX QD-OLED` результат полностью
подтверждён: firmware target — Novatek `NT68503`, общее имя runtime-платформы —
`NT68500`. Это согласуется с `docs/firmware-map.md` и сервисным меню живого
монитора.

## Realtek

| Монитор | Проверенная firmware MSI | Скалер | Признак |
|---|---|---|---|
| MAG 271QP QD-OLED X24 | [FW.011](https://download.msi.com/archive/frm_exe/monitor/MAG-271QP-QD-OLED-X24-FW.011-500B.zip), 2026-02-24 | `RTD2737`, target `RTD2737VD` | RTD |
| MAG 271QP QD-OLED X28 | [FW.012](https://download.msi.com/archive/frm_exe/monitor/MAG-271QP-QD-OLED-X28-FW.012-4261.zip), 2026-02-24 | `RTD2737` | RTD |
| MAG 271QPX QD-OLED E2 | [FW.028](https://download.msi.com/archive/frm_exe/monitor/MAG-271QPX-QD-OLED-E2-FW.028-CD2C.zip), 2026-02-24 | `RTD2738`, target `RTD2738VDC` | RTD |
| MAG 272QP QD-OLED X24 | [FW.012](https://download.msi.com/archive/frm_exe/monitor/MSI_MAG272QP_X24_V012_6B70.zip), 2026-07-21 | `RTD2721`, target `RTD2721-VD-CG` | RTD |
| MAG 272UP QD-OLED E16 | [FW.013](https://download.msi.com/archive/frm_exe/monitor/MAG272UP_E16_v013_7B16.zip), 2026-07-21 | `RTD2738`, target `RTD2738-VDC-CG` | RTD |
| MAG 274QP QD-OLED X24 | [FW.014](https://download.msi.com/archive/frm_exe/monitor/MAG-274QP-QD-OLED-X24-FW.014-551C.zip), 2026-02-24 | `RTD2721` | RTD |
| MAG 321CUP QD-OLED | [FW.014](https://download.msi.com/archive/frm_exe/monitor/MSI_MAG_321CUP_QD-OLED_FW.014_C155.zip), 2026-01-19 | `RTD2738`, target `RTD2738VDC` | RTD |
| MAG 321UP QD-OLED | [FW.020](https://download.msi.com/archive/frm_exe/monitor/MSI_MAG_321UP_QD-OLED_FW.020_F129.zip), 2026-01-19 | `RTD2738`, target `RTD2738VDC` | RTD |
| MAG 321UP QD-OLED X24 | [FW.012](https://download.msi.com/archive/frm_exe/monitor/MAG321UP_X24_v012_DC2A.zip), 2026-07-21 | `RTD2739`, target `RTD2739-LUF-CG` | RTD |
| MAG 341CQP QD-OLED X28 | [FW.012](https://download.msi.com/archive/frm_exe/monitor/MSI_MAG_341CQP_QD-OLED_X28_FW.012_4023.zip), 2026-08-14 | `RTD2711` | RTD |
| MPG 271QR QD-OLED X50 | [FW.020](https://download.msi.com/archive/frm_exe/monitor/MSI_MPG_271QR_QD-OLED_X50_FW.020_CE9E.zip), 2026-01-19 | `RTD2739`, target `RTD2739YUF` | RTD |
| MPG 271QRX QD-OLED | [FW.111](https://download.msi.com/archive/frm_exe/monitor/MPG-271QRX-QD-OLED-fw%20-v111.zip), 2026-08-10 | `RTD2738`, target `RTD2738-VDC-CG` | RTD |
| MPG 272URX QD-OLED | [FW.021](https://download.msi.com/archive/frm_exe/monitor/MPG272URX-V021-D9B0.zip), 2025-11-26 | `RTD2739`, target `RTD2739-YUF-CG` | RTD |
| MPG 322UR QD-OLED X24 | [FW.012](https://download.msi.com/archive/frm_exe/monitor/MSI_MPG_322UR_QD-OLED_X24_FW.012_1F84.zip), 2026-08-14 | `RTD2739`, target `RTD2739YUF` | RTD |
| MPG 322URX QD-OLED | [FW.024](https://download.msi.com/archive/frm_exe/monitor/MPG322URX-V024-1FDE.zip), 2025-11-26 | `RTD2739`, target `RTD2739-YUF-CG` | RTD |
| MPG 341CQR QD-OLED X36 | [FW.018](https://download.msi.com/archive/frm_exe/monitor/MPG-341CQR-QD-OLED-X36-V018-E564.zip), 2026-06-01 | `RTD2739`, target `RTD2739-YGF-CG` | RTD |

Пример: в `MPG 271QR X50 FW.020` строка `RTD2739YUF` обнаружена на
`0xF828` непосредственно после внутренних имён модели `MPG 271Q X50` и панели
`TPO265QH1-FG01`. В `MPG 272URX` аналогичный identity block содержит модель,
панель `SDC QMC265AA01-D01` и `RTD2739-YUF-CG`.

`tools/fwmap.py` к этим файлам неприменим: Realtek имеет другой формат.
Случайные partition ID, полученные при интерпретации байтов с `0x6000`, не
использовались.

## MStar / MediaTek

| Монитор | Проверенная firmware MSI | Скалер | Признак |
|---|---|---|---|
| MAG 273QP QD-OLED X24 | [FW.033/120](https://download.msi.com/archive/frm_exe/monitor/MAG_273QP_QD-OLED-X24-Firmware_v033_v120.zip), 2026-03-16 | `MST9U6` | BUILD |

Обе аппаратные ветки содержат:

- `MST9U6` на `0xFF00`;
- `MST9U6_SECU`;
- пути вида `src/MST9U/interrupt.c`;
- токен `MSTAR`.

FW.033 и FW.120 имеют разные build markers и, согласно PDF MSI, не являются
взаимозаменяемыми, но модель скалера одинакова.

## Аппаратные ветки

| Модель | Ветки | Различие |
|---|---|---|
| MAG 271QPX QD-OLED | 0XX/1XX и 2XX/3XX | `NT68551` → `NT68553`, плюс разные панели |
| MAG 321UPX QD-OLED | 0XX и 1XX | обе `NT68550`, разные панели |
| MPG 321CURX QD-OLED | 0XX и 1XX | обе `NT68550`, панели `AA01`/`AA02` |
| MAG 273QP QD-OLED X24 | 0XX и 1XX | обе `MST9U6`, разные firmware builds |

Следствие: каталог нельзя индексировать только по retail model. Для выбора
прошивки нужны как минимум model и branch текущей установленной версии.

## Анонсированные модели без публичной scaler firmware

У всех 30 моделей текущей игровой landing-страницы firmware опубликована. Без
публичной загрузки на дату исследования остались дополнительные позиции:

- `PRO MAX 341QPXW14G` — support API существует, downloads пусты;
- `PRO MAX 271UPXW12G` / global alias `271UPXW12I` — API существует,
  downloads пусты;
- [`MAG OLED 271QPX32`](https://www.msi.com/news/detail/MSI-MAG-OLED-271QPX32-Unveiled--The-World-s-First-27--WQHD-5-Layer-QD-OLED-Penta-Tandem--Gaming-Monitor-Powered-by-Samsung-Display-s-QD-OLED-Technology-148692) — анонс есть, support/API пока 404;
- [`MPG OLED 322URDX36`](https://www.msi.com/news/detail/The-World-s-First-Triple-Mode-QD-OLED-Gaming-Monitor--MPG-OLED-322URDX36-31-5-Inch-4K-360Hz-Debuts-at-COMPUTEX-2026-148961) — анонс есть, support/API пока 404;
- `MEG X 34-inch QD-OLED` — вероятное выставочное имя; support/API пока 404.

Пустой каталог означает только отсутствие публичного скачиваемого пакета. У
модели может существовать заводская, сервисная или ещё не опубликованная
firmware.

## Локальный архив

Скачанные пакеты, извлечённые payload и результаты первичного анализа хранятся
локально в `firmware_archive/msi/`. Каталог намеренно исключён из Git. Для
каждого release directory сохранены:

- исходный ZIP без переименования;
- scaler BIN и релевантная PDF-инструкция;
- `analysis.json` с provenance, SHA-256, сигнатурами и выводом;
- `SHA256SUMS`;
- stdout `tools/fwmap.py` для корректно распознанных Novatek-образов.

Производные `region_*.bin` не архивируются: они воспроизводимы и для
не-Novatek форматов могут выглядеть правдоподобно при неверной разметке.

## Ограничение результата

Firmware надёжно показывает, под какую модель скалера собран target. Это не
эквивалент фотографии маркировки корпуса или аппаратному silicon-ID. Возможны
совместимые silicon revisions под одним target name.

Для абсолютного BOM-утверждения нужны:

1. фотография маркировки микросхемы;
2. схема или BOM;
3. аппаратный silicon-ID.

В текущем проекте `NT68503` дополнительно подтверждён сервисным меню живого
`MPG 341CQPX`, но физическая маркировка закрыта припаянным радиатором — см.
`docs/hardware-boards.md`.
