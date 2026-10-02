# Скалеры в OLED-мониторах Dell и Alienware

Дата исследования: 2026-08-17.

## Краткий вывод

OLED-линейка Dell/Alienware не использует единую scaler-платформу. Проверка
официальных firmware-пакетов дала пять разных классов результата:

| Результат идентификации | Модели с публичной firmware |
|---|---|
| Realtek с точной моделью | `AW3423DWF` — `RTD2717Q`; `AW3425DW` — `RTD2737`; `AW2725DF` — `RTD2738` |
| Realtek, точная модель не раскрыта | `AW2725D` |
| MediaTek с точной моделью | `AW2725Q`, `AW3225QF` — `MT9810` |
| MStar/MediaTek, только семейство | `S3225QC` — `TSUM`/`MST9U` family |
| NVIDIA G-Sync module, silicon ID не раскрыт | `AW3423DW` |

Главное наблюдение: название серии и даже близость SKU не определяют скалер.
Например, `AW3423DW` обновляет NVIDIA G-Sync module, а `AW3423DWF` использует
Realtek `RTD2717Q`. В 27-дюймовых моделях одновременно встречаются Realtek
`RTD2738`, MediaTek `MT9810` и Realtek неизвестной точной модели.

Проверены 13 OLED-моделей Dell/Alienware. Для восьми найдена публичная firmware;
у пяти моделей публичного scaler-пакета на дату исследования нет. SHA-256 всех
восьми скачанных пакетов совпали со значениями на страницах Dell.

## Охват

Каталог составлен по официальным product и support pages Dell. Включены как
актуальные, так и значимые legacy OLED-модели.

| Модель | Панель | Статус | Публичная firmware | Вывод по скалеру |
|---|---|---|---|---|
| [UP3017Q](https://www.dell.com/support/product-details/en-us/product/up3017q-monitor/overview) | WOLED | legacy | нет | неизвестно |
| [AW3423DW](https://www.dell.com/support/product-details/en-us/product/aw3423dw-monitor/overview) | QD-OLED | legacy | `M0B205` | NVIDIA G-Sync module; silicon ID неизвестен |
| [AW3423DWF](https://www.dell.com/support/product-details/en-us/product/aw3423dwf-monitor/overview) | QD-OLED | legacy | `M3B107` | Realtek `RTD2717Q-VDL-CG` |
| [AW2725DF](https://www.dell.com/support/product-details/en-us/product/aw2725df-monitor/overview) | QD-OLED | current | `M3B105` | Realtek `RTD2738-WDL-CG` |
| [AW3225QF](https://www.dell.com/support/product-details/en-us/product/aw3225qf-monitor/overview) | QD-OLED | current | `M2B110` | MediaTek `MT9810TGQJNE` |
| [AW2725Q](https://www.dell.com/support/product-details/en-us/product/aw2725q-monitor/overview) | QD-OLED | current | `M2B102` | MediaTek `MT9810TGQJNE` |
| [AW2725D](https://www.dell.com/support/product-details/en-us/product/aw2725d-monitor/overview) | QD-OLED | current | `M3T102` | Realtek; точная модель неизвестна |
| [AW2726DM](https://www.dell.com/support/product-details/en-us/product/aw2726dm-monitor/overview) | QD-OLED | current | нет | неизвестно |
| [AW3425DW](https://www.dell.com/support/product-details/en-us/product/aw3425dw-monitor/overview) | QD-OLED | current | `M3B102` | Realtek `RTD2737-VDL-CG` |
| [AW3426DW](https://www.dell.com/support/product-details/en-us/product/aw3426dw-monitor/overview) | QD-OLED | current | нет | неизвестно |
| [AW3926QW](https://www.dell.com/support/product-details/en-us/product/aw3926qw-monitor/overview) | WOLED RGB-stripe tandem | current/regional | нет | неизвестно |
| [U3226Q](https://www.dell.com/support/product-details/en-us/product/u3226q-monitor/overview) | QD-OLED | current | нет | неизвестно |
| [S3225QC](https://www.dell.com/support/product-details/en-us/product/s3225qc-monitor/overview) | QD-OLED | current | `M3C107` | MStar/MediaTek `TSUM`/`MST9U` family; точная модель неизвестна |

`AW2725QF` намеренно исключён. Несмотря на похожее имя, официальная
[product page Dell](https://www.dell.com/en-us/shop/alienware-27-4k-dual-resolution-gaming-monitor-aw2725qf/apd/210-bnjj/monitors-monitor-accessories)
описывает его как dual-resolution **IPS** monitor, а не OLED.

## Официальные firmware-пакеты

Исследовалась последняя опубликованная scaler/monitor firmware для каждой
модели. Дата — дата публикации Dell, а не build date внутри payload.

| Модель | Firmware | Дата | Driver ID | Пакет | SHA-256 пакета |
|---|---|---:|---|---|---|
| AW3423DW | [M0B205](https://www.dell.com/support/home/en-us/drivers/driversdetails?driverid=k0phf) | 2023-12-05 | `K0PHF` | [ZIP](https://dl.dell.com/FOLDER10936663M/1/Alienware_MonitorFirmwareUpdateUtility_W_AW3423DW_M0B205.zip) | `4819489752bcad06a21a6af51e3d870bd86ccef9c42b8a0b29058d50f33d7b00` |
| AW3423DWF | [M3B107](https://www.dell.com/support/home/en-us/drivers/driversdetails?driverid=892hj) | 2024-04-16 | `892HJ` | [EXE](https://dl.dell.com/FOLDER11496815M/1/Alienware_AW3423DWF_FWUpdate_M3B107_Windows.exe) | `8c3f167ef636c99fea05a7fb8a4205320ff1731d6783d2480c6a4dbc6fd48d4e` |
| AW2725Q | [M2B102](https://www.dell.com/support/home/en-us/drivers/driversdetails?driverid=kknnd) | 2025-06-27 | `KKNND` | [EXE](https://dl.dell.com/FOLDER13305744M/1/Alienware_AW2725Q_FWUpdate_M2B102_Windows.exe) | `7c2249dfdd42f5abeb076360276f8933acec2368855bcc3a848d82219dd05759` |
| AW2725DF | [M3B105](https://www.dell.com/support/home/en-us/drivers/driversdetails?driverid=6278x) | 2026-03-30 | `6278X` | [EXE](https://dl.dell.com/FOLDER14357781M/1/Alienware_AW2725DF_FWUpdate_M3B105_Windows.exe) | `579168e00268f681b8d17d925bf7e1dde24bc464a3adff56089a1709613bd106` |
| S3225QC | [M3C107](https://www.dell.com/support/home/en-us/drivers/driversdetails?driverid=p95k5) | 2026-04-13 | `P95K5` | [EXE](https://dl.dell.com/FOLDER14417053M/1/Dell_S3225QC_FWUpdate_M3C107_Windows.exe) | `805d138bed5c5cc209a0efb11e8e354a38040e6b667e3361301bccd2fa269004` |
| AW3225QF | [M2B110](https://www.dell.com/support/home/en-us/drivers/driversdetails?driverid=rdxr8) | 2026-04-21 | `RDXR8` | [EXE](https://dl.dell.com/FOLDER14457752M/1/Alienware_AW3225QF_FWUpdate_M2B110_Windows.exe) | `826b828a9290473c76f2969551ca7d37df2b145c6341c6438d4f6e8f0924d11f` |
| AW3425DW | [M3B102](https://www.dell.com/support/home/en-us/drivers/driversdetails?driverid=hwtky) | 2026-04-23 | `HWTKY` | [EXE](https://dl.dell.com/FOLDER14465760M/1/Alienware_AW3425DW_FWUpdate_M3B102_Windows.exe) | `d0cf7587fa674c3b428793d283776af953f56cba21d7a5dfd1b15d76933d9190` |
| AW2725D | [M3T102](https://www.dell.com/support/home/en-us/drivers/driversdetails?driverid=vk08p) | 2026-04-30 | `VK08P` | [EXE](https://dl.dell.com/FOLDER14492619M/1/Alienware_AW2725D_FWUpdate_M3T102_Windows.exe) | `4cb37de17f1ad892027d15b2a75e912e4e3c5b9fb3db1db61e282f75cf059d1b` |

## Метод идентификации

1. Найти последнюю firmware на официальной support page модели.
2. Скачать пакет с `dl.dell.com`, передав browser User-Agent и Referer.
3. Сверить SHA-256 с хешем Dell до распаковки.
4. Распаковать пакет, не запуская Windows EXE/DLL:
   - RAR SFX с RAR6 compression — `unrar` 7.x;
   - NSIS/InstallShield — `7zz`;
   - `AW3423DW` — ZIP, затем NSIS updater и `gsfw` payload.
5. Отделить actual scaler firmware (`UPG`/`gsfw`) от updater, USB hub,
   audio, webcam, MCU и smart-OS payload.
6. Просканировать actual payload по ASCII и UTF-16LE на `RTDxxxx`, `MTxxxx`,
   `NTxxxxx`, `MSTxxxx`, `MStar`, `MediaTek`, `Realtek`, модель монитора,
   firmware version и panel ID.
7. Считать точную модель доказанной только тогда, когда identity находится
   внутри firmware payload рядом с monitor/version/segment context. Строки в
   updater DLL используются максимум как подтверждение семейства.
8. Проверить применимость `tools/fwmap.py`. Ни один Dell payload не содержит
   Novatek magic `55 AA 66 99`; случайную partition-разметку принимать нельзя.

Старый `p7zip`/`7za` и `unar` не распаковывали часть Dell RAR6 SFX корректно:
получались пустые или частичные UPG. Для этих пакетов результат подтверждался
только после `unrar` 7.x.

## Доказательства по моделям

### AW3423DW — NVIDIA G-Sync module, точная модель неизвестна

Пакет содержит Electron updater, `gsyncflash.exe` и один payload:

- файл `0xAC10_0xA1E4_8-200_6-20_0-3_1-21.gsfw`;
- размер 39 629 316 байт;
- SHA-256 `bc331ccea3215a112bd1b833accec2c2d554a1a1e5815d008eb3ae6102524d84`;
- magic `WFSG` @`0x0`;
- `Dell AW3423DW` @`0x8`;
- panel `SAM_QTM340YA01_3O40` @`0x50`.

`gsyncflash.exe` и формат `gsfw` доказывают, что обновляется NVIDIA G-Sync
module, выполняющий scaler-функции. В payload нет контекстной строки `RTD`,
`NT`, `MT` или иной точной модели silicon. Числа `0xAC10_0xA1E4` в имени —
USB VID/PID target updater, а не модель скалера.

**Уверенность:** высокая для типа NVIDIA module; точный silicon ID неизвестен.

### AW3423DWF — Realtek RTD2717Q

Payload `AW3423DWF_M3B107_20240130(ISP).UPG`:

- размер 3 674 180 байт;
- SHA-256 `96b95afbefacacedb9d77f25fe142755088d3783e64c5a2deda40ec9c8ce7808`;
- `M3B107` @`0x0`, восьмибайтовый target `AW3423DW` @`0x8`;
- `RTD2717Q-VDL-CG` @`0x21`, `0x71`, `0x1A9405`, `0x1F95AB`;
- поздние две копии сопровождаются полной строкой `M3B107AW3423DWF` и
  segment metadata.

**Вывод:** Realtek `RTD2717Q`, firmware variant `RTD2717Q-VDL-CG`.
**Уверенность:** высокая.

### AW3425DW — Realtek RTD2737

Payload `AW3425DW_M3B102_20260320(ISP)_0402.UPG`:

- размер 1 509 232 байта;
- SHA-256 `e44833de0472bb4b3b6f3c935c348927daf1971e5a013c28d6458c72209b158f`;
- `M3B102` @`0x0`, `AW3425DW` @`0x8`;
- `RTS5409S-VA` @`0x21`;
- `RTD2737-VDL-CG` @`0x71` и `0x62786`.

`RTD2737` — scaler target. `RTS5409S-VA` сохранён как отдельный Realtek
companion device неизвестной роли; наличие его строки в том же header не делает
его основным скалером.

**Вывод:** Realtek `RTD2737`, firmware variant `RTD2737-VDL-CG`.
**Уверенность:** высокая.

### AW2725DF — Realtek RTD2738

Payload `AW2725DF_M3B105_20260317(ISP).UPG`:

- размер 3 247 880 байт;
- SHA-256 `e9dbe1d2f9998d2810895f36ff7ae7dd73cf336c736bef34f4318289b81ba351`;
- `RTD2738-WDL-CG` @`0x21`, `0x71`, `0xC1`, `0x111`;
- `DELL MONITOR FIRMWARE` @`0x160`;
- `AW2725DF` @`0x8` и `0x180`.

Четыре одинаковых scaler identity records непосредственно связаны с моделью и
версией firmware.

**Вывод:** Realtek `RTD2738`, firmware variant `RTD2738-WDL-CG`.
**Уверенность:** высокая.

### AW2725D — Realtek, exact model unknown

Payload `AW2725D_M3T102_20260407.upg`:

- размер 1 545 091 байт;
- SHA-256 `6208dc4ad552aa07125487906d0fb628448721a25826b9e37f57e68793a3a5fe`;
- контейнер начинается с `UPG3`;
- Realtek scaler magic `@RTD` @`0x66836`;
- далее присутствует EDID monitor name `AW2725D`;
- основная часть образа имеет зашифрованные/high-entropy blocks.

Строки `Realtek BillBoard Device` ближе к концу относятся к USB Billboard и не
использовались как scaler evidence. Ни в payload, ни в распакованной updater
configuration нет контекстного `RTD27xx` part number.

**Вывод:** vendor Realtek; точная модель неизвестна.
**Уверенность:** высокая для vendor, отсутствует для exact model.

### AW2725Q — MediaTek MT9810

Payload `AW2725Q_M2B102_20250613_2(ISP).UPG`:

- размер 2 099 534 байта;
- SHA-256 `eb00b2c899467d2f095c5b3eca0b72fcbc507ac787c7bb8d2c9ec20ab258cbf8`;
- `M2B102` @`0x0`, `AW2725Q` @`0x8`;
- `RTS5409S-VA-GR` @`0x21`;
- `MT9810TGQJNE` @`0x71`;
- внутри scaler code также есть `src/MST9U/interrupt.c` и MStar HDCP strings.

Identity `MT9810TGQJNE` находится в monitor-specific header. Как и у
`AW3425DW`, `RTS5409S` — отдельный Realtek companion target, не основной
скалер.

**Вывод:** MediaTek `MT9810`, identity variant `MT9810TGQJNE`.
**Уверенность:** высокая.

### AW3225QF — MediaTek MT9810

Payload `AW3225QF_M2B110_20260401(ISP).UPG`:

- размер 6 688 766 байт;
- SHA-256 `b9697b238f7114f9d6310bf5873fa3eff43b885c4b9d859cc95ba21cd7716ef3`;
- `MT9810TGQJNE` @`0x21`, `0x71`, `0xC1`, `0x111`, `0x161`, `0x1B1`;
- `DELL MONITOR FIRMWARE` @`0x200`;
- `AW3225QF` @`0x8` и `0x220`;
- `M2B110_ISP` находится в том же identity area.

Предыдущий `M2B107` содержал тот же `MT9810TGQJNE` в первых четырёх records;
обновление до `M2B110` добавило ещё два segment records, но scaler target не
изменило.

**Вывод:** MediaTek `MT9810`, identity variant `MT9810TGQJNE`.
**Уверенность:** высокая.

### S3225QC — MStar/MediaTek family, exact model unknown

`S3225QC` — многокомпонентный smart monitor. Пакет содержит scaler firmware,
Realtek ALC4058 audio firmware, SunplusIT SPCA2650 webcam firmware и отдельный
NXP i.MX8MN smart-platform boot/root filesystem. Последние три компонента не
являются основным display scaler.

Scaler payload `S3225QC_M3C107_ISP_202603241.UPG`:

- размер 8 136 564 байта;
- SHA-256 `6cb98a8484e90dc1e6e27ea82fbe797c87070c992ea80b396d50821137775f73`;
- `[DELL MONITOR UPG FILE CONFIG]` @`0x0`;
- `S3225QC` @`0x22`, `M3C107` @`0x32`;
- после header @`0x100` — encrypted/obfuscated body с энтропией 7.9364
  bit/byte; контекстной chip identity нет.

Updater-side `DELL_IspLibrary.dll` содержит `SOC_MSTAR`, `MST9U series`,
`TSUM series` и `ScalarProductPartNumIndex`. Это подтверждает MStar/MediaTek
family ISP path, но библиотека поддерживает несколько семейств и не доказывает
конкретный part number данного экземпляра.

**Вывод:** MStar/MediaTek `TSUM`/`MST9U` family; exact model unknown.
**Уверенность:** средняя для family, отсутствует для exact model.

## Ложные признаки

При анализе Dell-пакетов отдельно исключались:

- `RtHIDlib.dll`, USB VID/PID и `RT Hub` — updater transport или companion
  Realtek device, не автоматическое доказательство Realtek scaler;
- `MCHP_ISP_API`, `mchp_hub_isp*` — Microchip USB-hub ISP;
- `TUSB8044_I2C_API` — Texas Instruments USB hub;
- `CxAudioHid` и `ALC4058` — audio components;
- `SunplusCamera` и `SPCA2650` — webcam controller;
- `MST2SST`/`SST2MST` — DisplayPort topology, не MStar chip identity;
- случайные `RTD`/`MT` byte sequences в encrypted/high-entropy data;
- `Mapping.txt`, `U3425WE`, `Flash.dat`, updater EXE/DLL и installer metadata;
- NXP i.MX8MN boot/rootfs в `S3225QC` — smart-platform SoC, отдельный от
  display scaler.

## Модели без публичной scaler firmware

На дату исследования публичного firmware download не найдено для:

- legacy `UP3017Q`;
- `AW2726DM`;
- `AW3426DW`;
- `AW3926QW`;
- `U3226Q`.

Это означает только отсутствие публичного скачиваемого пакета. У модели может
существовать factory/service firmware или пакет, который Dell ещё не
опубликовала.

## Ограничение результата

Firmware надёжно показывает build target, когда part identity записана рядом с
моделью монитора и version/segment metadata. Это всё равно не фотография
маркировки корпуса и не аппаратный silicon-ID: под одним firmware target могут
существовать совместимые silicon revisions.

Для `AW2725D`, `S3225QC` и NVIDIA module в `AW3423DW` точную модель нельзя
честно вывести из доступного payload. Для абсолютного BOM-утверждения нужны:

1. фотография маркировки микросхемы;
2. схема или BOM платы;
3. аппаратный silicon-ID или vendor-specific debug response.
