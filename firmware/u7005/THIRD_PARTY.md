# Зависимости и лицензии

Код этого каталога (кроме явно указанных зависимостей) — MIT, см. LICENSE.

- NUC1261BSP `94bfd7c4cf92f08b7e7c6ab155f2991848a9ba4c`: драйверы CLK, UART,
  I2C, USBD, `system_NUC1261.c`, заголовки устройства.
  Copyright (C) Nuvoton Technology Corp. Apache-2.0 согласно заголовкам исходников.
  [Исходники](https://github.com/OpenNuvoton/NUC1261BSP/tree/94bfd7c4cf92f08b7e7c6ab155f2991848a9ba4c),
  [текст Apache-2.0](licenses/Apache-2.0.txt).
- CMSIS Core 4.30 из того же BSP: copyright 2009–2015 ARM Limited,
  BSD-3-Clause согласно заголовкам; [текст](licenses/CMSIS-BSD.txt).
- newlib-nano и libgcc из Arm GNU Toolchain 15.3.Rel1: сохраняются лицензии комплекта,
  включая разрешительные лицензии newlib и GCC Runtime Library Exception для libgcc.
  Их исходники и notices доступны в поставке/документации
  [Arm GNU Toolchain](https://developer.arm.com/Tools%20and%20Software/GNU%20Toolchain).

Зависимости подключаются из `U7005_BSP` и локального toolchain, исходные файлы
поставщиков не меняются. Закрытого машинного кода MSI в образе приложения нет;
USB-дескрипторы и параметры протокола воспроизведены для совместимости. Лицензия
проекта не распространяется на эталонные дампы MSI и захваты из других каталогов.
