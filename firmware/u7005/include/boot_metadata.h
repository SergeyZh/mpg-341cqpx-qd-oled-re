/* SPDX-License-Identifier: MIT */
#ifndef U7005_BOOT_METADATA_H
#define U7005_BOOT_METADATA_H
#include <stdbool.h>
#include <stdint.h>
#define U7005_USB_LENGTH 0x1f7f8u
/* Called before USB/MSC or any mutable settings are exposed. */
bool boot_metadata_prepare(uint32_t code_length,
    bool (*read_word)(uint32_t address,uint32_t *value),
    bool (*write_metadata)(const uint32_t words[2]));
#endif
