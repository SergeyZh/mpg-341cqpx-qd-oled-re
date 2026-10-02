# Среда разработки прошивки U7005

Установлена и проверена 2026-09-14 на macOS arm64. Выбран C11,
Arm GNU Toolchain, CMake/Ninja и официальный NUC1261BSP.
Собственное приложение находится в [firmware/u7005](../firmware/u7005/README.md):
оно собирается и проходит программные проверки, аппаратный запуск ещё не проверен.
Аппаратная база — [U7005](mcu-u7005.md), загрузка и обновление —
[LDROM](u7005-ldrom.md).

## Установленные компоненты

| Компонент | Версия | Размещение |
|---|---|---|
| Arm GNU Toolchain | 15.3.Rel1, GCC 15.3.1 | `out/deps/arm-gnu-toolchain-15.3.rel1-darwin-arm64-arm-none-eabi/` |
| GDB из того же комплекта | 16.3.90.20250906-git | `bin/arm-none-eabi-gdb` внутри toolchain |
| CMake | 4.4.3 | Homebrew, `/opt/homebrew/bin/cmake` |
| Ninja | 1.13.2 | Homebrew, `/opt/homebrew/bin/ninja` |
| NUC1261BSP | `94bfd7c4cf92f08b7e7c6ab155f2991848a9ba4c` | `out/deps/NUC1261BSP-94bfd7c4cf92f08b7e7c6ab155f2991848a9ba4c/` |
| pyOCD | 0.45.1 | корневая `.venv/`, уже был установлен |
| hidapi | 0.15.0 | корневая `.venv/`, уже был установлен |
| pyelftools | 0.33 | корневая `.venv/`, уже был установлен |
| pytest | 9.1.1 | корневая `.venv/`, установлен при подготовке |

Комплект Arm включает binutils, GDB, заголовки и библиотеки newlib/newlib-nano.
PKG-установка через Homebrew потребовала административный пароль и не завершилась;
использован официальный архив Arm, распакованный в проект. Глобальный PATH не менялся.
Архивы и распакованные зависимости в `out/` не коммитятся.

## Использование

Из корня репозитория:

```sh
tools/u7005-env.sh arm-none-eabi-gcc --version
tools/u7005-env.sh arm-none-eabi-gdb --version
tools/u7005-env.sh cmake --version
.venv/bin/python -m pyocd --version
.venv/bin/python -m pip check
```

`tools/u7005-env.sh <команда> [аргументы...]` добавляет локальные `.venv/bin`
и `toolchain/bin` в PATH только запускаемого процесса и задаёт `U7005_BSP`.
Это исполняемая обёртка, её не нужно подключать через `source`.
Python-модули устанавливать только через `.venv/bin/python -m pip`.
Прямые Python-зависимости закреплены в `tools/requirements-u7005.txt`;
это не полный lock транзитивных зависимостей.

## Повторная установка

На macOS Apple Silicon, из корня репозитория:

```sh
brew install cmake ninja
.venv/bin/python -m pip install -r tools/requirements-u7005.txt
mkdir -p out/deps
curl -fL 'https://gitlab.arm.com/api/v4/projects/tooling%2Fgnu-toolchains-for-arm/packages/generic/gnu-toolchain/15.3.rel1/arm-gnu-toolchain-15.3.rel1-darwin-arm64-arm-none-eabi.tar.xz' -o out/deps/arm-gnu-toolchain-15.3.rel1-darwin-arm64-arm-none-eabi.tar.xz
curl -fL 'https://github.com/OpenNuvoton/NUC1261BSP/archive/94bfd7c4cf92f08b7e7c6ab155f2991848a9ba4c.tar.gz' -o out/deps/NUC1261BSP-94bfd7c4.tar.gz
shasum -a 256 out/deps/arm-gnu-toolchain-15.3.rel1-darwin-arm64-arm-none-eabi.tar.xz out/deps/NUC1261BSP-94bfd7c4.tar.gz
# Сверить хеши ниже перед распаковкой.
tar -xJf out/deps/arm-gnu-toolchain-15.3.rel1-darwin-arm64-arm-none-eabi.tar.xz -C out/deps
tar -xzf out/deps/NUC1261BSP-94bfd7c4.tar.gz -C out/deps
```

SHA-256 полученных по HTTPS архивов (локальная фиксация, не отдельная проверка подписи):

```text
376808a59ca209c1413236f1c6a509e33da4b29857ab28642b9927cf3048af55  arm-gnu-toolchain-15.3.rel1-darwin-arm64-arm-none-eabi.tar.xz
122e028428c5125e4512e60725e764965451b7947d5435d11e09d66d6ead05af  NUC1261BSP-94bfd7c4.tar.gz
```

Версии Homebrew-компонентов в таблице описывают установленное окружение;
`brew install` при повторении может установить более новые версии.
Источник BSP и его лицензия — [официальный репозиторий Nuvoton](https://github.com/OpenNuvoton/NUC1261BSP/tree/94bfd7c4cf92f08b7e7c6ab155f2991848a9ba4c).

## Что проверено

- GCC и GDB запускаются на этом Mac; CMake использует локальный ARM-компилятор.
- CMake/Ninja успешно собрали `system_NUC1261.c` и драйверы USBD, UART, I2C,
  CLK, FMC с `-mcpu=cortex-m0 -mthumb -std=c11`.
- Пробный ELF с вызовами BSP и `memcpy` слинкован с newlib-nano, получены BIN
  и map. GDB читает символы и дизассемблирует `Reset_Handler`; ELF имеет
  атрибуты v6S-M и Thumb-1. Пробные файлы — `out/u7005-toolchain-check/`.
- Импорт pyOCD, hidapi, pyelftools и pytest из `.venv` успешен; `pip check`
  не нашёл несовместимых зависимостей.
- `tools/verify_u7005_ldrom_read.py` прошёл существующую проверку на модели FMC.

Пробный ELF проверяет только инструменты и не предназначен для загрузки в монитор:
в нём нет полноценного startup, инициализации платы или протокола MSI.
Доступа к железу и записи Flash при подготовке среды не было.

В BSP файл `Library/Device/Nuvoton/NUC1261/Source/GCC/gcc_arm.ld`
объявляет 256 КиБ Flash. Для нашего NE4AE его нельзя использовать без адаптации:
физически есть 128 КиБ, а также области режима USB, метаданных и Data Flash
внутри APROM, описанные в разборе LDROM. Пробная сборка использовала отдельный
скрипт с границей Flash `0x1E800` и RAM 20 КиБ.

pyOCD с generic-таргетом `cortex_m` подходит для отладки, но не предоставляет
алгоритм записи Flash. Установка среды этого ограничения не снимает.
Текущий `tools/u7005_isp.py` также не содержит команд записи прошивки.
