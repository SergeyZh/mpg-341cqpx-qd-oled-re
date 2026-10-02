/* SPDX-License-Identifier: MIT */

#include <stdint.h>
#include "nt68503.h"
#include "uart.h"

#define UART_BAUD_RATE      4800UL
#define UART_TIMER_DIVISOR  384UL
#define UART_TIMER_MODULUS  256UL
#define UART_CLOCK_48MHZ_HZ 48000000UL
#define UART_CLOCK_96MHZ_HZ 96000000UL
#define UART_RELOAD(clock_hz) \
    (UART_TIMER_MODULUS - \
     ((clock_hz) * 2UL / UART_TIMER_DIVISOR / UART_BAUD_RATE))

enum {
    UART_RELOAD_48MHZ = UART_RELOAD(UART_CLOCK_48MHZ_HZ),
    UART_RELOAD_96MHZ = UART_RELOAD(UART_CLOCK_96MHZ_HZ),
};

#define UART_XON  0x11u
#define UART_XOFF 0x13u

void uart_init(uint8_t variant)
{
    /*
     * Before stbc-main changes the clock tree, the timer source is derived
     * from 48 MHz on variant 0x20 and from 96 MHz on the installed 0x17 part.
     * UART_RELOAD performs the vendor calculation at compile time:
     * clock * 2 / 384 / baud, then the 8-bit reload is 256 - result.
     */
    TH1 = variant == 0x20u ? UART_RELOAD_48MHZ : UART_RELOAD_96MHZ;
    SCON = 0x52;
    TMOD = 0x21;
    PCON = 0x80;
    TR1 = 1;
}

void uart_putc(char c)
{
    uint8_t received;

    /* Preserve the stock bootloader's software flow control on the debug RX. */
    if (RI && SBUF == UART_XOFF) {
        RI = 0;
        do {
            while (!RI) {
            }
            received = SBUF;
            RI = 0;
        } while (received != UART_XON);
    }

    while (!TI) {
    }
    TI = 0;
    SBUF = (uint8_t)c;
}

void uart_puts(const char __code *text)
{
    while (*text != '\0') {
        uart_putc(*text++);
    }
}

void uart_drain(void)
{
    /* uart_putc waits before a byte; wait once more for the final LF. */
    while (!TI) {
    }
}

static char hex_digit(uint8_t value)
{
    value &= 0x0Fu;
    return value < 10u ? (char)('0' + value) : (char)('A' + value - 10u);
}

void uart_hex8(uint8_t value)
{
    uart_putc(hex_digit(value >> 4));
    uart_putc(hex_digit(value));
}

void uart_hex16(uint16_t value)
{
    uart_hex8((uint8_t)(value >> 8));
    uart_hex8((uint8_t)value);
}
