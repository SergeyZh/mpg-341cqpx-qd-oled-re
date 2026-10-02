/* SPDX-License-Identifier: MIT */
#ifndef U7005_BOARD_H
#define U7005_BOARD_H
#include "bridge.h"
extern struct bridge bridge;
extern const struct bridge_io board_io;
void board_init(void);
bool board_prepare_image(void);
void board_poll(void);
uint32_t board_millis(void);
void board_delay(uint32_t ms);
void usb_init(uint8_t mode);
void usb_poll(void);
bool usb_send(const uint8_t report[64]);
bool usb_idle(void);
void usb_request_mode(uint8_t mode);
void usb_disconnect(void);
void msc_reset(void);
void msc_out(const uint8_t *data, size_t length);
size_t msc_in(uint8_t *data);
bool msc_in_pending(void);
void disk_read(uint32_t sector,uint8_t *data);
bool disk_write(uint32_t sector,const uint8_t *data);
bool msc_halted(void);
#define DISK_SECTORS 44u
#endif
