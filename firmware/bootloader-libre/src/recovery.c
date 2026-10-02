/* SPDX-License-Identifier: MIT
 *
 * Early joystick selection and the autonomous USB-ISP recovery path.
 */

#include <stdint.h>
#include "gpio.h"
#include "nt68503.h"
#include "recovery.h"
#include "timing.h"
#include "uart.h"

#define GPIO_SETTLE_PERIODS 3u
#define USB_RESET_PERIODS  12u
#define ARRAY_SIZE(array) ((uint8_t)(sizeof(array) / sizeof((array)[0])))

/* GPIO functions established by reversible tests on the live FW.034 monitor. */
#define GPIO_VL211_ENABLE         GPIO_PIN(4u, 4u)
#define GPIO_U7005_ENABLE         GPIO_PIN(13u, 5u)
#define GPIO_VL211_USB_B_SELECT   GPIO_PIN(3u, 2u)
#define GPIO_VL211_RESET          GPIO_PIN(10u, 4u)

/* Required by Main's sequence, but their exact electrical roles are unknown. */
#define GPIO_USB_INIT_BANK6_BIT7  GPIO_PIN(6u, 7u)
#define GPIO_USB_INIT_BANK7_BIT0  GPIO_PIN(7u, 0u)
#define GPIO_USB_INIT_BANK5_BIT4  GPIO_PIN(5u, 4u)
#define GPIO_ACTIVE_BANK4_BIT7    GPIO_PIN(4u, 7u)
#define GPIO_ACTIVE_BANK13_BIT0   GPIO_PIN(13u, 0u)

/*
 * Full board states are retained verbatim because most pins in these banks
 * have not been identified. REG3 enables strong HIGH drive on tested GPIO8.0;
 * the banks below have not been electrically characterized, so keep the name.
 */
static const struct gpio_bank_state __code cold_usb_gpio_table[] = {
    /* bank, REG3, DATA, DIR (1=input, 0=output) */
    { 4u,  0x50u, 0xAFu, 0x0Cu },
    { 6u,  0x83u, 0x7Cu, 0x74u },
    { 7u,  0x70u, 0x8Eu, 0xC2u },
    { 5u,  0x10u, 0xFFu, 0x2Fu },
    { 13u, 0x31u, 0xDEu, 0x42u },
};

static const struct gpio_bank_state __code usb_mode_gpio_table[] = {
    /* bank, REG3, DATA, DIR (1=input, 0=output) */
    { 3u,  0x04u, 0xF3u, 0xFBu },
    { 10u, 0xE3u, 0x1Cu, 0xE4u },
};

static void apply_gpio_table(const struct gpio_bank_state __code *table,
                             uint8_t count)
{
    uint8_t i;

    for (i = 0u; i < count; ++i) {
        gpio_apply_bank_state(&table[i]);
    }
}

static void apply_cold_usb_gpio_table(void)
{
    /*
     * A warm reset can preserve the later high levels.  Applying the cold
     * table first creates real reset/enable edges instead of merely rewriting
     * the already-active state.
     */
    apply_gpio_table(cold_usb_gpio_table, ARRAY_SIZE(cold_usb_gpio_table));
}

static void enable_vl211_and_u7005(void)
{
    /* GPIO4.4 controls VL211; GPIO13.5 controls U7005 while VL211 stays up. */
    gpio_configure(GPIO_VL211_ENABLE, GPIO_OUTPUT_HIGH);
    gpio_configure(GPIO_USB_INIT_BANK6_BIT7, GPIO_OUTPUT_HIGH);
    gpio_configure(GPIO_USB_INIT_BANK7_BIT0, GPIO_OUTPUT_HIGH);
    delay_recovery_periods(GPIO_SETTLE_PERIODS);

    gpio_configure(GPIO_USB_INIT_BANK5_BIT4, GPIO_OUTPUT_HIGH);
    gpio_configure(GPIO_U7005_ENABLE, GPIO_OUTPUT_HIGH);

    /* This pair selects active over power-save state; exact circuitry is unknown. */
    gpio_configure(GPIO_ACTIVE_BANK4_BIT7, GPIO_OUTPUT_LOW);
    delay_recovery_periods(GPIO_SETTLE_PERIODS);
    gpio_configure(GPIO_ACTIVE_BANK13_BIT0, GPIO_OUTPUT_HIGH);
}

static void select_usb_b_and_reset_vl211(void)
{
    apply_gpio_table(usb_mode_gpio_table, ARRAY_SIZE(usb_mode_gpio_table));

    gpio_configure(GPIO_VL211_USB_B_SELECT, GPIO_OUTPUT_HIGH);
    gpio_configure(GPIO_VL211_RESET, GPIO_OUTPUT_LOW);
    delay_recovery_periods(USB_RESET_PERIODS);
    gpio_write(GPIO_VL211_RESET, GPIO_HIGH);
}

static void enable_raw_service_i2c(void)
{
    /* Disable service UART 4 and release its pin pair. */
    xwrite(REG_SERVICE_UART, xread(REG_SERVICE_UART) & 0x7Fu);
    xwrite(REG_SERVICE_UART_AUX, 0xF0u);
    xwrite(REG_SERVICE_PINMUX, xread(REG_SERVICE_PINMUX) & 0xBFu);

    /* Reset the old slave channel, then arm raw-I2C channel 1 at 0x6E. */
    xwrite(REG_SLAVE0_RESET_A, xread(REG_SLAVE0_RESET_A) & 0x7Fu);
    xwrite(REG_SLAVE0_RESET_B, xread(REG_SLAVE0_RESET_B) & 0x7Fu);
    xwrite(REG_RAW_SLAVE_ADDR, 0x6Fu);
    xwrite(REG_RAW_SLAVE_DATA, 0xFFu);
    xwrite(REG_RAW_SLAVE_CFG, 0xF8u);
    xwrite(REG_RAW_SLAVE_CTRL, xread(REG_RAW_SLAVE_CTRL) | 0x40u);
}

static void recovery_hardware_init(void)
{
    apply_cold_usb_gpio_table();
    delay_recovery_periods(GPIO_SETTLE_PERIODS);
    enable_vl211_and_u7005();
    select_usb_b_and_reset_vl211();
    enable_raw_service_i2c();
}

static void uart_report_gpio_bank(const char __code *name,
                                  gpio_bank_t bank)
{
    uart_puts("libre: gpio");
    uart_puts(name);
    uart_putc(' ');
    uart_hex8(gpio_read_reg3(bank));
    uart_putc(' ');
    uart_hex8(gpio_read_data(bank));
    uart_putc(' ');
    uart_hex8(gpio_read_direction(bank));
    uart_puts("\r\n");
}

static void uart_report_recovery_gpio(void)
{
    uart_report_gpio_bank("3", 3u);
    uart_report_gpio_bank("10", 10u);
    uart_report_gpio_bank("4", 4u);
    uart_report_gpio_bank("6", 6u);
    uart_report_gpio_bank("7", 7u);
    uart_report_gpio_bank("5", 5u);
    uart_report_gpio_bank("13", 13u);
}

void joystick_init(void)
{
    /* Same ADC setup used by Main, limited to joystick channel 5. */
    xwrite(REG_ADC_CTRL_0, 0u);
    xwrite(REG_ADC_CTRL_2, 0x80u);
    xwrite(REG_ADC_CTRL_3, 1u);
    xwrite(REG_ADC_ENABLE_H, xread(REG_ADC_ENABLE_H) | 1u);
    xwrite(REG_ADC_CTRL_1, 0x1Bu);
}

uint8_t joystick_report(void)
{
    uint8_t adc = xread(REG_ADC_KEY);
    uint8_t direction = 0u;

    /* Live monitor mapping: right, left, down, up for ranges 1 through 4. */
    if ((uint8_t)(adc - 0x25u) < 0x2Du) {
        direction = JOYSTICK_RIGHT;
    } else if ((uint8_t)(adc - 0x60u) < 0x25u) {
        direction = JOYSTICK_LEFT;
    } else if ((uint8_t)(adc - 0x93u) < 0x1Du) {
        direction = JOYSTICK_DOWN;
    } else if ((uint8_t)(adc - 0xBDu) < 0x17u) {
        direction = JOYSTICK_UP;
    }

    if (direction != 0u) {
        uart_puts("libre: joystick direction ");
        uart_putc((char)('0' + direction));
        uart_puts(" adc ");
        uart_hex8(adc);
        uart_puts("\r\n");
    }

    return direction;
}

void enter_recovery(void)
{
    recovery_hardware_init();
    uart_report_recovery_gpio();
    uart_puts("libre: ISP ready\r\n");

    for (;;) {
        xwrite(REG_UNKNOWN_F00A, F00A_STOCK_POLL_VALUE);
    }
}
