# Возможность обновления LDROM в NUC1261

Разбор 2026-09-14. Объект — даташит NUC126 и официальный BSP Nuvoton, не прошивка MSI.

## Краткий ответ

**LDROM — это Flash-память (4 КБ), а не заводская mask-ROM.** Обновление
возможно аппаратно, но по умолчанию заблокировано битом `LDUEN`.

## Что такое FMC

**FMC** — Flash Memory Controller, встроенный контроллер Flash-памяти в кристалле
NUC1261. Через его регистры выполняются все операции с внутренней Flash: чтение,
стирание, программирование и управление загрузкой.

Ключевые регистры FMC:

| Регистр | Назначение |
|---------|-----------|
| `FMC_ISPCTL` | Управление: `ISPEN`, `BS`, биты `*UEN` (разрешение обновления областей) |
| `FMC_ISPTRG` | Триггер запуска операции (`ISPGO`) |
| `FMC_ISPSTS` | Статус: `ISPFF` (ошибка), `VECMAP`, `DFBA` |
| `FMC_ISPCMD` | Команда: READ / ERASE / PROGRAM |
| `FMC_ISPADDR` | Адрес операции |
| `FMC_ISPDAT` | Данные для записи/чтения |

Типичный цикл операции FMC:

```
1. Разблокировать регистры SYS (0x59A7, 0x05A7, 0x5AA5 в SYS_AWPC)
2. FMC_ISPCMD  = команда (READ / ERASE / PROGRAM)
3. FMC_ISPADDR = целевой адрес
4. FMC_ISPDAT  = данные (для PROGRAM)
5. FMC_ISPTRG |= ISPGO              ← триггер запуска
6. Ждать, пока (FMC_ISPSTS & ISPFF) == 0
7. Заблокировать регистры SYS (0x53F8 в SYS_PWPK)
```

## Доказательства из даташита

Источник: `datasheets/DS_NUC126_Series_EN_Rev1.05.pdf` (Rev 1.05, Apr. 08, 2020).

**Раздел 6.4.1 Overview:**

> The NUC126 series is equipped with 128/256 KB on-chip embedded Flash for
> application and configurable Data Flash to store some application dependent
> data. A User Configuration block provides for system initiation. A 4 KB loader
> ROM (LDROM) is used for In-System-Programming (ISP) function.

Нюанс: термин "ROM" здесь — маркетинговое обозначение. Даташит называет LDROM
Flash, а не mask-ROM:

**Раздел 6.4.2 Features:**

> Supports 4 KB Flash for loader (LDROM)

**Регистр `FMC_ISPCTL` (таблица регистров, стр. 73):**

| Бит | Имя | Описание |
|-----|-----|----------|
| [5] | `LDUEN` | **LDROM Update Enable Bit** (Write Protect) |
| [4] | `CFGUEN` | CONFIG Update Enable Bit (Write Protect) |
| [3] | `APUEN` | APROM Update Enable Bit (Write Protect) |
| [2] | `SPUEN` | SPROM Update Enable Bit (Write Protect) |
| [1] | `BS` | Boot Select (Write Protect) |
| [0] | `ISPEN` | ISP Enable Bit (Write Protect) |

Наличие отдельного бита `LDUEN` — прямое подтверждение, что LDROM
программируем. Mask-ROM не нуждается в бите разрешения обновления.

## Механизм из BSP Nuvoton

Источник: репозиторий `OpenNuvoton/NUC1261BSP` (коммит 94bfd7c4, 2016).

**`fmc.h`** — макросы для управления LDROM:

```c
#define FMC_ENABLE_LD_UPDATE()    (FMC->ISPCTL |=  FMC_ISPCTL_LDUEN_Msk)
#define FMC_DISABLE_LD_UPDATE()   (FMC->ISPCTL &= ~FMC_ISPCTL_LDUEN_Msk)
```

Документация к `FMC_ENABLE_LD_UPDATE()`:

> This function will set LDUEN bit of ISPCTL control register to enable
> LDROM update function. User needs to set LDUEN bit before they can
> update LDROM.

Документация к `FMC_DISABLE_LD_UPDATE()`:

> Disable LDROM update function will forbid LDROM programming.
> LDROM update is default to be disable.

**`fmc.c`** — функции реализации:

```c
void FMC_EnableLDUpdate(void)
{
    FMC->ISPCTL |= FMC_ISPCTL_LDUEN_Msk;
}

void FMC_DisableLDUpdate(void)
{
    FMC->ISPCTL &= ~FMC_ISPCTL_LDUEN_Msk;
}
```

Стандартные функции FMC (`FMC_Write`, `FMC_Erase`, `FMC_ProgramMulti`)
работают с LDROM так же, как с APROM и Data Flash — при условии, что `LDUEN`
установлен. Адрес LDROM: `0x00100000` (константа `FMC_LDROM_BASE` в `fmc.h`).

## Что делает эталонный загрузчик ISP_HID

Референсный загрузчик `SampleCode/ISP/ISP_HID/main.c` **не устанавливает LDUEN**.
В `main()`:

```c
FMC->ISPCTL |= FMC_ISPCTL_ISPEN_Msk;  // только ISPEN
```

Перед переходом в APROM:

```c
FMC->ISPCTL &= ~(FMC_ISPCTL_ISPEN_Msk | FMC_ISPCTL_BS_Msk);
```

Значит стандартный USB-HID загрузчик Nuvoton обновляет только APROM и Data Flash.
LDROM он не трогает. Для обновления LDROM нужен отдельный загрузчик, который
устанавливает `LDUEN`.

## Что делает кастомный загрузчик MSI

Наш LDROM (версия 15, дамп `flash/u7005_ldrom_fmc.bin`) — это **кастомный загрузчик
MSI**, а не стандартный `ISP_HID`. Разобран в [u7005-ldrom.md](u7005-ldrom.md).

В диспетчере команд ISP загрузчика MSI **нет команды для обновления LDROM**.
Установленный бит `LDUEN` отсутствует: при чтении через SWD `ISPCTL=0x00`
(только `ISPEN` установлен, `LDUEN=0`).

## Как можно обновить LDROM

1. **Через USB-ISP** — невозможно с текущим загрузчиком MSI. Нет команды, нет `LDUEN`.
2. **Через SWD (pyOCD/CMSIS-DAP)** — возможно. Внешний отладчик пишет напрямую
   в регистры FMC:
   - Разблокировать `SYS`
   - `FMC->ISPCTL |= LDUEN_Msk` — разрешить обновление LDROM
   - Стереть страницу LDROM (2 КБ, адрес `0x100000`)
   - Записать новый образ (4 КБ)
   - Сбросить `LDUEN`, если нужно
3. **Через ISP-программатор Nu-Link-2** — Nu-Link-2 поддерживает режим ISP для
   NUC1261 и может устанавливать `LDUEN` через JTAG/SWD, минуя загрузчик.
   Однако стандартная утилита NuComm2 ориентирована на APROM; для LDROM нужен
   ручной сценарий.

## Риски

- Если LDROM повреждён и `LDUEN` сброшен, USB-ISP недоступен. Единственный путь
  восстановления — SWD/JTAG, который может записать в регистры FMC напрямую.
- LDROM занимает всего 4 КБ. Страница Flash — 2 КБ, значит стирание одной страницы
  `0x100000` уберёт половину; полный образ 4 КБ требует двух страниц.
- После обновления LDROM нужно убедиться, что `BS` (Boot Select) и `CONFIG0`
  настроены правильно, иначе чип может не загрузиться.

## Состояние на нашем мониторе

По данным [u7005-ldrom.md](u7005-ldrom.md) и [mcu-u7005.md](mcu-u7005.md):

- `ISPCTL` при чтении через SWD = `0x00000000` (все биты сброшены).
- `LDUEN = 0` — обновление LDROM заблокировано.
- `BS = 0` — загрузка из APROM.
- `CONFIG0.LOCK = 1` (бит 0 в `FFFFFB7E` — инвертирован, LOCK=1).

Загрузчик MSI не использует `LDUEN` и не предоставляет путь к его установке.
Обновить LDROM можно только через SWD.
