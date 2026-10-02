#!/bin/sh
# Запуск инструментов U7005 с локальным Arm GNU Toolchain и проектной .venv.
set -eu
U7005_REPO_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
U7005_TOOLCHAIN="$U7005_REPO_ROOT/out/deps/arm-gnu-toolchain-15.3.rel1-darwin-arm64-arm-none-eabi"
export U7005_BSP="$U7005_REPO_ROOT/out/deps/NUC1261BSP-94bfd7c4cf92f08b7e7c6ab155f2991848a9ba4c"
if [ ! -x "$U7005_TOOLCHAIN/bin/arm-none-eabi-gcc" ]; then
    echo "Не установлен Arm GNU Toolchain: см. docs/u7005-development.md" >&2
    exit 1
fi
PATH="$U7005_REPO_ROOT/.venv/bin:$U7005_TOOLCHAIN/bin:$PATH"
export PATH
if [ "$#" -eq 0 ]; then
    echo "Использование: tools/u7005-env.sh <команда> [аргументы...]" >&2
    exit 2
fi
exec "$@"
