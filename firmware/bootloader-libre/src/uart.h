/* SPDX-License-Identifier: MIT */
#ifndef UART_H
#define UART_H

#include <stdint.h>

/* Initialize the pre-main 4800-baud UART for the detected clock variant. */
void uart_init(uint8_t variant);

/* Blocking output; uart_putc also honors the stock XOFF/XON protocol. */
void uart_putc(char c);
void uart_puts(const char __code *text);

/* Wait for the last byte written by uart_putc before handing control to F1D. */
void uart_drain(void);

void uart_hex8(uint8_t value);
void uart_hex16(uint16_t value);

#endif
