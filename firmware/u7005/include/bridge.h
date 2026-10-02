/* SPDX-License-Identifier: MIT */
#ifndef U7005_BRIDGE_H
#define U7005_BRIDGE_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define HID_SIZE 64u
#define STREAM_CAPACITY 4160u
#define PAGE_SIZE 512u
#define EXT_VERSION 1u
#define EXT_DATA_OFFSET 12u
#define EXT_DATA_SIZE (HID_SIZE - EXT_DATA_OFFSET)
enum ext_status { EXT_OK, EXT_BAD_REQUEST, EXT_WRONG_MODE, EXT_IO_ERROR,
                  EXT_BAD_REPLY, EXT_NO_PAGE, EXT_BAD_TOKEN };
/* No packed/native structs on the wire. HAL calls execute in the main loop. */
struct bridge_io {
    bool (*send)(const uint8_t report[HID_SIZE]);
    bool (*uart_write)(unsigned port, const uint8_t *data, size_t length);
    void (*uart_clear)(unsigned port);
    bool (*i2c_write)(unsigned bus, const uint8_t *wire, size_t length, bool nack_start);
    bool (*i2c_read)(unsigned bus, uint8_t address8, uint8_t *data, size_t length);
    bool (*i2c_register_read)(unsigned bus, uint8_t address7, uint8_t reg,
                              uint8_t *data, size_t length);
    void (*delay_ms)(uint32_t ms);
    bool (*set_mode)(bool i2c);
    uint32_t (*flash_read)(uint32_t address);
    bool (*settings_write)(unsigned offset, const uint8_t *data, size_t length);
    bool (*usb_mode_write)(uint8_t mode);
    void (*enter_ldrom)(void);
};
struct stream {
    uint8_t data[STREAM_CAPACITY];
    uint16_t length;
    uint8_t family;
    bool active;
};
struct bridge {
    const struct bridge_io *io;
    struct stream uart, i2c;
    uint8_t settings[13], usb_mode, hardware_revision, uart_subcommand;
    uint8_t macro_event, aux_event, aux_connected;
    uint16_t aux_value;
    uint32_t aux_timeout;
    bool i2c_mode, page_valid;
    uint16_t page_token;
    uint32_t page_address;
    uint8_t page[515]; /* len, B5, 512 data bytes, XOR; SLA+R is not received. */
};
extern const uint8_t msi_uart_lengths[36], msi_i2c_lengths[36], msi_read_lengths[36];
void bridge_init(struct bridge *b, const struct bridge_io *io);
void bridge_reset_transport(struct bridge *b);
void bridge_report(struct bridge *b, const uint8_t *report, size_t length);
void bridge_uart_received(struct bridge *b, unsigned port, const uint8_t *data, size_t length);
void bridge_macro_event(struct bridge *b);
void bridge_tick(struct bridge *b,uint32_t elapsed_ms);
#endif
