# Скалеры в OLED-мониторах Samsung

Дата исследования: 2026-08-17.

## Краткий вывод

OLED-линейка Samsung не использует единую scaler-платформу. По официальным
прошивкам обнаружены два внешних производителя скалеров, а в Smart/Tizen
моделях точный scaler скрыт шифрованием общего системного образа.

| Результат идентификации | Модели |
|---|---|
| Novatek `NT68550`, firmware target, средняя уверенность | `G93SC`, `G93SD`, `G91SD`, `G60SD`, `G61SD`, `G73SH` |
| MStar/MediaTek `MST9U6`, высокая уверенность | `G81SF` 27″/32″, `G60SF` |
| Smart/Tizen, scaler не извлекается из AES-зашифрованной firmware | `G85SB`, `G95SC`, `G95SD`, `G85SD`, `G80SD`, `M90SF` |
| Публичной MAIN firmware нет | `G80SH` 27″/32″, `G61SH` |

Таким образом, среди 16 исследованных OLED-семейств:

- 14 имеют публичную firmware;
- 8 дают открытый standalone scaler payload;
- 6 публикуют зашифрованный Smart/Tizen system image;
- 2 пока не имеют публичного MAIN-пакета.

Главное наблюдение совпадает с результатами MSI и Dell: название серии не
определяет scaler. Например, `G60SD` использует firmware target Novatek
`NT68550`, а следующее поколение `G60SF` — MStar/MediaTek `MST9U6`.
Внутри серии G8 модель `G81SF` использует `MST9U6`, тогда как Smart-модели
`G85SB`, `G85SD` и `G80SD` обновляются общим зашифрованным Tizen-образом, из
которого scaler честно определить нельзя.

## Охват

Каталог составлен по официальным product и support pages Samsung. Региональные
суффиксы `SNXZA`, `SUXXU`, `SMXUE`, `SCXXK` и аналогичные объединены, когда они
относятся к одному retail/chassis family. Панель OLED не выводилась из
универсальных OLED Care FAQ: Samsung показывает такие статьи и на страницах
не-OLED моделей.

| Модель | Панель | Год/статус | Публичная firmware | Вывод по скалеру |
|---|---|---|---|---|
| [Odyssey OLED G8 G85SB](https://www.samsung.com/ca/support/model/LS34BG850SNXZA/) | 34″ QD-OLED | 2023, legacy | `1720.7` | неизвестно: AES-encrypted Smart/Tizen image |
| [Odyssey OLED G9 G95SC](https://www.samsung.com/ca/support/model/LS49CG954SNXZA/) | 49″ QD-OLED | 2023, legacy | `2000.2` | неизвестно: AES-encrypted Smart/Tizen image |
| [Odyssey OLED G9 G93SC](https://www.samsung.com/levant/support/model/LS49CG934SMXUE/) | 49″ QD-OLED | 2023, legacy | `1011.0` | Novatek `NT68550`, средняя уверенность |
| [Odyssey OLED G9 G95SD](https://www.samsung.com/hk_en/support/model/LS49DG952SCXXK/) | 49″ QD-OLED | 2024, current | `2000.2` | неизвестно: AES-encrypted Smart/Tizen image |
| [Odyssey OLED G9 G93SD](https://www.samsung.com/uk/support/model/LS49DG934SUXXU/) | 49″ QD-OLED | 2024, current | `1005.0 / 1005.0` | две Novatek-ветки, обе target `NT68550` |
| [Odyssey OLED G9 G91SD](https://www.samsung.com/ca/support/model/LS49DG912SNXZA/) | 49″ QD-OLED | 2024, current | `1003.2` | Novatek `NT68550`, средняя уверенность |
| [Odyssey OLED G8 G85SD](https://www.samsung.com/ca/support/model/LS34DG850SNXZA/) | 34″ QD-OLED | 2024, current | `1340.1` | неизвестно: AES-encrypted Smart/Tizen image |
| [Odyssey OLED G8 G80SD](https://www.samsung.com/ca/support/model/LS32DG802SNXZA/) | 32″ QD-OLED | 2024, current | `1340.1` | неизвестно: AES-encrypted Smart/Tizen image |
| [Odyssey OLED G6 G60SD](https://www.samsung.com/ca/support/model/LS27DG602SNXZA/) | 27″ QD-OLED | 2024, current | `1006.0` | Novatek `NT68550`, средняя уверенность |
| [Odyssey OLED G6 G61SD](https://www.samsung.com/ca/support/model/LS27DG61DSNXZA/) | 27″ QD-OLED | 2024, current | `1004.2` | Novatek `NT68550`, средняя уверенность |
| [Odyssey OLED G8 G81SF](https://www.samsung.com/ca/support/model/LS32FG810SNXZA/) | 27″/32″ QD-OLED | 2025, current | `1001.0 / 1003.0` | MStar/MediaTek `MST9U6` |
| [Odyssey OLED G6 G60SF](https://www.samsung.com/ca/support/model/LS27FG600SNXZA/) | 27″ QD-OLED | 2025, current | `1002.9` | MStar/MediaTek `MST9U6` |
| [Smart Monitor M9 M90SF](https://www.samsung.com/uk/support/model/LS32FM902SUXXU/) | 32″ QD-OLED | 2025, current | `0090-1296.8` | неизвестно: AES-encrypted Smart/Tizen image |
| [Odyssey OLED G8 G80SH](https://www.samsung.com/ca/support/model/LS32HG802SNXZA/) | 27″/32″ QD-OLED | 2026, current | нет | неизвестно |
| [Odyssey OLED G7 G73SH](https://www.samsung.com/ca/support/model/LS32HG730SNXZA/) | 32″ QD-OLED | 2026, current | `1002.0` | Novatek `NT68550`, средняя уверенность |
| [Odyssey OLED G6 G61SH](https://www.samsung.com/ca/support/model/LS27HG612SNXZA/) | 27″ QD-OLED | 2026, current | нет | неизвестно |

Отдельно проверены и исключены как не-OLED:

- `Odyssey 3D G90XF` — IPS;
- `Odyssey G9 G91F` — VA/LCD, не путать с OLED `G91SD`;
- `Odyssey G8 G80HS` — 6K Fast IPS;
- `Smart Monitor M8 M80C/M80D/M80F` — VA/LCD.

## Метод

Для каждой модели проверялась официальная support page и download category.
Из firmware исключались device driver, Samsung Display Manager, Easy Setting
Box, руководства и отдельные camera/lens updates.

Standalone ZIP обрабатывались так:

1. ZIP скачивался по официальному `downloadcenter.samsung.com` URL.
2. Проверялись CRC каждого member и отсутствие path traversal.
3. Вычислялся SHA-256 ZIP и каждого извлечённого payload.
4. Проверялись container magic, ASCII и UTF-16LE строки, build/project records.
5. Искались `NTxxxxx`, `Novatek`, `RTDxxxx`, `Realtek`, `MST...`, `MStar`,
   `MediaTek`, `MTK`, `SCALER` и `PANEL` с byte offsets и контекстом.
6. `tools/fwmap.py` запускался только как дополнительная проверка Novatek layout;
   его NT68503-specific partition parser не переносился на Samsung вслепую.

Smart/Tizen ZIP имеют размер около 1.64–1.73 ГБ каждый. Для новых веток ZIP
был разобран удалённо через HTTP Range: EOCD, central directory, `info.txt` и
начало `upgrade.msd`. Сервер вернул `206 Partial Content`. Полностью скачаны и
захешированы два representative packages — `G85SB` и `G95SC`; остальные
Smart-пакеты не скачивались целиком, поскольку заголовок и `info.txt` уже
доказывают шифрование всего payload, а дополнительные гигабайты не раскрывают
scaler.

Samsung не публикует SHA-256. Все приведённые SHA-256 вычислены локально по
фактически полученным байтам.

## Официальные firmware packages

### Открытые standalone scaler packages

| Модель | Версия/дата | Официальный пакет | Размер ZIP | SHA-256 ZIP |
|---|---|---|---:|---|
| `G93SC` | `1011.0`, 2026-03-09 | [`M-C9349GGAA.zip`](https://org.downloadcenter.samsung.com/downloadfile/ContentsFile.aspx?CDSite=UNI_LEVANT&OriginYN=N&ModelType=N&ModelName=S49CG934SM&CttFileID=10469310&CDCttType=FM&VPath=FM%2F202603%2F20260309103255153%2FM-C9349GGAA.zip) | 2,455,509 | `3c63b0e2d250d6901e57de7be3b24ec2981162de3df5cef6b666896cf7f59c54` |
| `G60SD` | `1006.0`, 2026-01-28 | [`M-D6027GGAA.zip`](https://org.downloadcenter.samsung.com/downloadfile/ContentsFile.aspx?CDSite=UNI_CA&OriginYN=N&ModelType=N&ModelName=S27DG602SN&CttFileID=9888080&CDCttType=FM&VPath=FM%2F202601%2F20260128172747617%2FM-D6027GGAA.zip) | 2,439,692 | `53cb202b76416244a2993fe68303db69d3b0f133c510167eb81378ba9c832d22` |
| `G61SD` | `1004.2`, 2025-10-21 | [`M-D6127GGAA.zip`](https://org.downloadcenter.samsung.com/downloadfile/ContentsFile.aspx?CDSite=UNI_CA&OriginYN=N&ModelType=N&ModelName=S27DG61DSN&CttFileID=10095973&CDCttType=FM&VPath=FM%2F202510%2F20251021093624871%2FM-D6127GGAA.zip) | 2,354,156 | `a051c87ca88bc6f9803ab49cb1c3990e9ea4259851a65244d855c837cd74a1b8` |
| `G91SD` | `1003.2`, 2025-11-01 | [`M-D9149GGAA-1003.2[9224].zip`](https://org.downloadcenter.samsung.com/downloadfile/ContentsFile.aspx?CDSite=UNI_CA&OriginYN=N&ModelType=N&ModelName=S49DG912SN&CttFileID=11177489&CDCttType=FM&VPath=FM%2F202511%2F20251102072932802%2FM-D9149GGAA-1003.2%5B9224%5D.zip) | 1,162,036 | `b77c87852373a312191acb95ec0783af250981f11f3dbcc85e4924cd421d7869` |
| `G93SD` | `1005.0 / 1005.0`, 2026-03-09 | [`update_File.zip`](https://org.downloadcenter.samsung.com/downloadfile/ContentsFile.aspx?CDSite=UNI_UK&OriginYN=N&ModelType=N&ModelName=S49DG934SU&CttFileID=10871305&CDCttType=FM&VPath=FM%2F202603%2F20260309102557783%2Fupdate_File.zip) | 4,888,616 | `398183bacd1499a4a25a4750c0af3b641e508a2069ad0e48bfef8e35fa6dd37a` |
| `G81SF` | `1001.0 / 1003.0`, 2025-09-12 | [`Update_File.zip`](https://org.downloadcenter.samsung.com/downloadfile/ContentsFile.aspx?CDSite=UNI_CA&OriginYN=N&ModelType=N&ModelName=S32FG810SN&CttFileID=10864610&CDCttType=FM&VPath=FM%2F202509%2F20250912164249044%2FUpdate_File.zip) | 5,302,489 | `958f34c33ee929235f6ea4c3d1ff775e43555c5488d3aaebe753cce4905563ab` |
| `G60SF` | `1002.9`, 2025-08-19 | [`M-F6027GCZZ.zip`](https://org.downloadcenter.samsung.com/downloadfile/ContentsFile.aspx?CDSite=UNI_CA&OriginYN=N&ModelType=N&ModelName=S27FG600SN&CttFileID=10290230&CDCttType=FM&VPath=FM%2F202508%2F20250819090005270%2FM-F6027GCZZ.zip) | 2,695,444 | `230cd620fed8544e1338ea38f7946d5dd5764d156ed9d937988cce531ca73158` |
| `G73SH` | `1002.0`, 2026-04-29 | [`M-H7332GGZA.zip`](https://org.downloadcenter.samsung.com/downloadfile/ContentsFile.aspx?CDSite=UNI_CA&OriginYN=N&ModelType=N&ModelName=S32HG730SN&CttFileID=11399158&CDCttType=FM&VPath=FM%2F202604%2F20260429171950597%2FM-H7332GGZA.zip) | 1,187,202 | `82340e46f47a43a4022448f7379bf9aaa18ff760f195642f643c5a173effb6ca` |

### Зашифрованные Smart/Tizen packages

| Модель | Ветка | Версия/дата | Размер ZIP | Результат |
|---|---|---|---:|---|
| `G85SB` | [`T-PTMLWWC.zip`](https://org.downloadcenter.samsung.com/downloadfile/ContentsFile.aspx?CDSite=UNI_CA&OriginYN=N&ModelType=N&ModelName=S34BG850SN&CttFileID=10903498&CDCttType=FM&VPath=FM%2F202605%2F20260507113142612%2FT-PTMLWWC.zip) | `1720.7`, 2026-05-07 | 1,660,619,394 | `MSDU11` + AES; full ZIP SHA-256 `55d2a125733aa4fbaf2d3b8d67102a30859cf77498b438f31b162c50409c58d0` |
| `G95SC` | [`T-OSCSCWWC.zip`](https://org.downloadcenter.samsung.com/downloadfile/ContentsFile.aspx?CDSite=UNI_CA&OriginYN=N&ModelType=N&ModelName=S49CG954SN&CttFileID=9242073&CDCttType=FM&VPath=FM%2F202409%2F20240909162752634%2FT-OSCSCWWC.zip) | `2000.2`, 2024-09-09 | 1,731,498,040 | `MSDU11` + AES; full ZIP SHA-256 `6dee718c1a7b62f0cea343e1c9b81a9c003c19c455b62f965d01730b9510ff24` |
| `G95SD` | [`T-OSCSCWWC_.zip`](https://org.downloadcenter.samsung.com/downloadfile/ContentsFile.aspx?CDSite=UNI_HK_EN&OriginYN=N&ModelType=N&ModelName=S49DG952SC&CttFileID=11434186&CDCttType=FM&VPath=FM%2F202605%2F20260514151413242%2FT-OSCSCWWC_.zip) | `2000.2`, 2026-05-14 | 1,731,498,040 | `MSDU11` + AES; range-only |
| `G85SD` | [`T-PTMLDWWC.zip`](https://org.downloadcenter.samsung.com/downloadfile/ContentsFile.aspx?CDSite=UNI_CA&OriginYN=N&ModelType=N&ModelName=S34DG850SN&CttFileID=10580663&CDCttType=FM&VPath=FM%2F202604%2F20260421090145079%2FT-PTMLDWWC.zip) | `1340.1`, 2026-04-21 | 1,657,937,252 | `MSDU11` + AES; range-only |
| `G80SD` | [`T-RSPDWWC.zip`](https://org.downloadcenter.samsung.com/downloadfile/ContentsFile.aspx?CDSite=UNI_CA&OriginYN=N&ModelType=N&ModelName=S32DG802SN&CttFileID=10003531&CDCttType=FM&VPath=FM%2F202604%2F20260421101517666%2FT-RSPDWWC.zip) | `1340.1`, 2026-04-21 | 1,709,928,158 | `MSDU11` + AES; range-only |
| `M90SF` | [`T-RSPMFWWC-0090.zip`](https://org.downloadcenter.samsung.com/downloadfile/ContentsFile.aspx?CDSite=UNI_UK&OriginYN=N&ModelType=N&ModelName=S32FM902SU&CttFileID=10580767&CDCttType=FM&VPath=FM%2F202605%2F20260514113927080%2FT-RSPMFWWC-0090.zip) | `0090-1296.8`, 2026-05-14 | 1,639,111,887 | `MSDU11` + AES; range-only |

## Novatek NT68550

Шесть Samsung OLED families используют Novatek `NVTSC_IMG` или совместимый
Novatek flash layout. Во всех образах встречаются две разные категории строк:

1. generic SDK/platform strings `NT68500_TK_USB_IMG`, `NT68500 MCU Test
   program`, `NT68500 Leon2M/Leon2S`;
2. project-specific recovery target `NT68550_SSG..._RECOVER_<date>`.

Первая категория не доказывает установленный `NT68500`. Те же строки находятся
в исследованной MSI firmware, где точный `SCALER` config и сервисное меню
показывают `NT68503`. Поэтому в Samsung точным firmware target считается
`NT68550` из recovery project, но уверенность оставлена **средней**: это всё ещё
не фотография микросхемы и не аппаратный silicon-ID.

| Модель/payload | `NT68550` evidence | Generic `NT68500_TK_USB_IMG` | SHA-256 payload |
|---|---|---|---|
| `G93SC` `M-C9349GGAA-1011.0[C10A].img` | `NT68550_SSG93SD_RECOVER_20240607` @`0x302B0` | @`0x2F360` | `de1e93809ec4d06ca9920d3b17daba52f520532bb7d2e19d3bbffce76f70ba8c` |
| `G60SD` `M-D6027GGAA-1006.0[6023].img` | `NT68550_SSG60SD_RECOVER_20231214` @`0x31468` | @`0x2F520` | `740c42158f1d91ffde668fe5896b419d17fcd63930d701a694523a498ac8ae2d` |
| `G61SD` `M-D6127GGAA-1004.2[2E0C].img` | `NT68550_SSG60SD_RECOVER_20231214` @`0x31708` | @`0x2F7C0` | `0ec4ff15d42584a6106fab202babae676f9889b508698e7f912a9a006babf55d` |
| `G91SD` `M-D9149GGAA-1003.2[9224].img` | `NT68550_SSG60SD_RECOVER_20231214` @`0x314C8` | @`0x2F580` | `3388e5b622bfe2a3e3405c1efae023c1da75d397ddfa27931eab6d7ca1f30884` |
| `G93SD` `M-D9349GGAA-1005.0[8DE6].img` | `NT68550_SSG93SD_RECOVER_20240607` @`0x302B0` | @`0x2F360` | `a70f656d07fb71663a3bee3ed2efcc99f36b518963386d7daaf104807f16521a` |
| `G93SD` `M-D9349GGAB-1005.0[E473].img` | `NT68550_SSG93SD_RECOVER_20240607` @`0x302B0` | @`0x2F360` | `b4a8fa606b014240dd4b659e9871b7a2ab602b88c9148b22006230d2b8d2410d` |
| `G73SH` `M-H7332GGZA-1002.0[6395].img` | `NT68550_SSG60SD_RECOVER_20231214` @`0x2E438` | @`0x2CE80` | `82ab114ba262d74615e5514dd41548053a35407f157040d3795f2829782c839c` |

`G93SD` latest package содержит две scaler-ветки `GGAA` и `GGAB`. Обе имеют
один target `NT68550`; назначение различия `AA/AB` из firmware однозначно не
следует. Пакет также содержит:

- `MD49C0364C2503262810.bin`, SHA-256
  `996da95c37c7c9aa88089892cb2fdf97ab2fc268eada4842b5d5b19cbb2c1e66`;
- `SD49C0364C2503262810.bin`, SHA-256
  `cfcd3fe33004ad4b983b6027819c68b9762d41005107ea2645f693675859d5dc`.

Это Samsung Display OLED TCON images с `ZZ A5 A5` magic, Samsung/panel strings
и `DQHD(VD)`. Они относятся к panel timing controller, а не являются третьим
типом скалера.

## MStar/MediaTek MST9U6

`G81SF` и `G60SF` используют MStar/MediaTek `MST9U6`. Здесь доказательство
сильнее, чем у Novatek Samsung-образов: по смещению `0xFF00` находится
NUL-разделённый chip-marking block:

```text
MST9U6 \0 BGA \0 D43200e/D42666e \0 96 \0 00000000
```

Дополнительные признаки:

- `MST9U6_SECU` @`0x286FB1` в обеих `G81SF` ветках;
- `MST9U6_SECU` @`0x27F599` в `G60SF`;
- source paths `src/MST9U/interrupt.c`;
- `MSTAR_SECURE_STORE_FILE_MAGIC_ID`;
- MediaTek capability strings `MTK-HDMI21`, `MTK8K:DSC`, `MTK 4K`.

| Модель/payload | Ветка | Marking | SHA-256 payload |
|---|---|---|---|
| `G81SF` `M-F8100GCAA-1003.0[3761].bin` | 32″ | `MST9U6`, `D43200e` | `c8792779c992efbec801baa08f630b45691ef7c17e2fb1e446e38fbc0567ef56` |
| `G81SF` `M-F8127GCAB-1001.0[1833].bin` | 27″ | `MST9U6`, `D42666e` | `00468e9f949cf5c93c961f8790a08f333c53c1df23bd61337661b47863e85191` |
| `G60SF` `M-F6027GCZZ-1002.9[C543].bin` | 27″ | `MST9U6`, `D42666e` | `02955a7eeeabaa794465594a616cc450a67caf6c9db10c0cd75e442eeda0605b` |

`D43200e` и `D42666e` фиксируются как значения marking/build block, но не
объявляются аппаратными silicon revisions без datasheet или маркировки корпуса.
Строка `MStar_MST9U4-V10` — библиотечная/reference constant: она встречается
рядом с secure-store кодом и не отменяет прямую маркировку `MST9U6`.

## Smart/Tizen: почему scaler остаётся неизвестным

У всех пяти уникальных Tizen-веток payload начинается одинаковой структурой:

```text
0x0000  MSDU11
0x00DB  T-<branch code>
...     Salted__
```

| Модель | Branch code | `Salted__` offset | Cipher из `info.txt` |
|---|---|---:|---|
| `G85SB` | `T-PTMLWWC` | `0xEC` | `aes-256-cbc-sha512` |
| `G95SC` | `T-OSCSCWWC` | `0xED` | `aes-256-cbc-sha512` |
| `G95SD` | `T-OSCSCWWC` | `0xED` | `aes-256-cbc-sha512` |
| `G85SD` | `T-PTMLDWWC` | `0xED` | `aes-256-cbc-sha512` |
| `G80SD` | `T-RSPDWWC` | `0xEC` | `aes-256-cbc-sha512` |
| `M90SF` | `T-RSPMFWWC-0090` | `0xF2` | `aes-256-cbc-sha512` |

`info.txt` для всех веток перечисляет один и тот же набор partitions
`123456789101213141518192223`. Имена ключей `PONTUSML`, `Chipset_name`,
`PontusML 2024 TV`, `ROSEP 2024` и `RoseP 2025` не являются model ID скалера.
После `Salted__` находится ciphertext; поиск `Novatek`, `MStar`, `Realtek` или
коротких model-like tokens внутри него статистически даст случайные совпадения.

`G95SC` и `G95SD` публикуют один `T-OSCSCWWC` firmware code. Их `info.txt`
совпадает, включая внутренний MD5 `5c4394ad9d5c0c49dccc0b6a022c422c`, размеры
members и начало payload. Это сильное свидетельство общей firmware branch, но
для range-only `G95SD` полный SHA-256 не приписывается: одинаковый MD5 из
metadata и первые байты не заменяют локальный SHA-256 всего файла.

## Аппаратные и package-ветки

- `G60SD` и `G61SD` используют разные firmware names:
  `M-D6027GGAA` и `M-D6127GGAA`. Cross-flash по близости названий недопустим.
- `G60SD/G61SD` используют Novatek target `NT68550`; `G60SF` следующего
  поколения перешёл на `MST9U6`.
- `G81SF` один `Update_File.zip` содержит две отдельные ветки: 32″ `F8100` и
  27″ `F8127`. Обе используют `MST9U6`, но payload и marking/build values
  различаются.
- `G93SD` один `update_File.zip` содержит `GGAA`, `GGAB` и две TCON firmware.
- Smart `G95SC` и `G95SD` используют общую `OSCS` branch, но это не разрешение
  на cross-flash: updater дополнительно проверяет model/chassis metadata.
- `G80SD` 2024, `G80SH` 2026 и LCD `G80HS` — разные chassis families.

## Ложные признаки

При автоматическом поиске нельзя считать model evidence следующие строки:

- `NT68500 MCU Test program`, `NT68500_TK_USB_IMG`, `NT68500 Leon2M/Leon2S` —
  общий Novatek SDK/platform слой;
- `MStar_MST9U4-V10` — reference/library constant рядом с прямой маркировкой
  `MST9U6`;
- `Samsung`, panel codes, `DQHD(VD)` в `MD...`/`SD...` — признаки TCON;
- `Chipset_name rel key`, `PONTUSML`, `ROSEP` — имена ключей Tizen update;
- короткие ASCII-совпадения внутри AES ciphertext;
- firmware filename `M-...` или retail series name без in-payload identity.

## Модели без публичной MAIN firmware

На дату исследования официальные Canadian support pages показывают:

- `G80SH`: Samsung Display Manager, device driver, manuals; category
  `Upgrade File(USB), MAIN` отсутствует;
- `G61SH`: Samsung Display Manager, device driver, repair/user manuals; MAIN
  firmware отсутствует.

Это означает только отсутствие публичного скачиваемого пакета на дату
проверки. Factory/service firmware или будущий public update могут существовать.

## Локальный архив

Игнорируемый Git локальный архив находится в `firmware_archive/samsung/`.
Для восьми standalone releases сохраняются:

- исходный ZIP без переименования;
- непосредственные scaler/TCON payloads;
- `analysis.json` с provenance, SHA-256, byte offsets и выводом;
- `SHA256SUMS`.

Для Smart/Tizen используется компактная схема:

- полные ZIP `G85SB` и `G95SC`, уже использованные для representative check;
- `info.txt` и первые байты `upgrade.msd` для всех шести моделей;
- range acquisition metadata для четырёх не скачанных целиком пакетов;
- без дублирования multi-GB extracted ciphertext.

Производные `region_*.bin`, `stbc*` и `leon*` не архивируются.

## Ограничение результата

Firmware показывает, под какой scaler target собран updater. Для `MST9U6`
прямой chip-marking block даёт высокую уверенность в точной модели firmware
platform. Для Samsung Novatek точная модель выводится только из
product/recovery target `NT68550_SSG...`; поэтому уверенность средняя.

Ни один firmware-вывод не эквивалентен фотографии маркировки корпуса или
аппаратному silicon-ID. Под одним target могут существовать совместимые silicon
revisions. Для Smart/Tizen AES-шифрование не позволяет определить даже vendor
скалера из публичного payload.

Для абсолютного BOM-утверждения нужны:

1. фотография маркировки микросхемы;
2. схема или BOM платы;
3. аппаратный silicon-ID или vendor-specific debug response;
4. для Smart/Tizen — легитимно расшифрованный image или сервисный dump.
