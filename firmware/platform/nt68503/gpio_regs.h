/* SPDX-License-Identifier: MIT */
#ifndef NT68503_GPIO_REGS_H
#define NT68503_GPIO_REGS_H
/* 8051 XDATA aliases. Bank numbers are1..17; these unchecked constant
 * expressions require a bank in the indicated group. DIR bit1=input.
 * DATA reads physical pads; release input latches HIGH during output RMW.
 * Evidence and pad measurements: docs/gpio.md, docs/nt68503-hardware.md. */
#define NT_GPIO_COUNT 17u
/* Leon2 word-stride alias of the GPIO XDATA registers below. */
#define NT_GPIO_AHB(xdata_address) (0xCF000000UL + 4UL * (xdata_address))
#define NT_GPIO_DATA_1_5(b) (0xF000u + (b) - 1u)
#define NT_GPIO_DIR_1_5(b)  (0xF005u + (b) - 1u)
#define NT_GPIO_DATA_6_7(b) (0xF010u + ((b) - 6u) * 2u)
#define NT_GPIO_DIR_6_7(b)  (NT_GPIO_DATA_6_7(b) + 1u)
#define NT_GPIO_DATA_8_13(b) (0xF114u + ((b) - 8u) * 2u)
#define NT_GPIO_DIR_8_13(b)  (NT_GPIO_DATA_8_13(b) + 1u)
#define NT_GPIO_DATA_14_17(b) (0xF300u + (b) - 14u)
#define NT_GPIO_DIR_14_17(b)  (0xF310u + (b) - 14u)
#define NT_GPIO_REG3_1_7(b) (0xF0B0u + (b) - 1u)
#define NT_GPIO_REG3_8_13(b) (0xF130u + (b) - 8u)
#define NT_GPIO_REG3_14_17(b) (0xF320u + (b) - 14u)
#define NT_GPIO_REG4_1_5(b) (0xF0C7u + (b) - 1u)
/* F0CC/F0CD are not REG4 of banks6/7. */
#define NT_GPIO_REG4_6_7(b) (0xF0CEu + (b) - 6u)
#define NT_GPIO_REG4_8_13(b) (0xF138u + (b) - 8u)
#define NT_GPIO_REG4_14_17(b) (0xF330u + (b) - 14u)
#endif
