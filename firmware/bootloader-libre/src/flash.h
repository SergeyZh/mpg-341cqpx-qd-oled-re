/* SPDX-License-Identifier: MIT */
#ifndef FLASH_H
#define FLASH_H

#include <stdint.h>
#include "spi_nor.h"

#define FLASH_INDEX_GD25Q256 0x87u
#define FLASH_ERASE_4K       SPI_NOR_CMD_SECTOR_ERASE_4K
#define FLASH_SIZE_CLASS     0x05u

/* Enable the controller aperture and reset its FIFO. */
void flash_controller_init(void);

/* Read JEDEC, latch it for stbc-main and accept only the installed GD25Q256E. */
uint8_t flash_is_supported(void);

/* Read or update the volatile 16-MiB Extended Address Register. */
uint8_t flash_get_bank(void);
void flash_set_bank(uint8_t bank);

/* Enable QE when needed, then prove Quad, Dual or serial reads against CODE. */
void flash_configure_bus(void);

#endif
