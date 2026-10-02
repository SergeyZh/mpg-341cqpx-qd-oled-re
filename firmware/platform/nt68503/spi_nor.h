/* SPDX-License-Identifier: MIT */
#ifndef SPI_NOR_H
#define SPI_NOR_H

/* Device commands sent on the SPI wires, NOT NT68503 controller commands.
 * Source: GD25Q256E Rev1.1, tables 10/11, sections 6.1 and 7.
 * Subset used by bootloader/STBC, including the boot ABI erase opcode.
 */
#define SPI_NOR_CMD_WRSR1              0x01u /* Write Status Register-1 */
#define SPI_NOR_CMD_PAGE_PROGRAM      0x02u /* Page Program */
#define SPI_NOR_CMD_FAST_READ          0x0Bu /* Fast Read */
#define SPI_NOR_CMD_RDSR1              0x05u /* Read Status Register-1 */
#define SPI_NOR_CMD_WREN               0x06u /* Write Enable */
#define SPI_NOR_CMD_SECTOR_ERASE_4K    0x20u /* Sector Erase */
#define SPI_NOR_CMD_RDSR2              0x35u /* Read Status Register-2 */
#define SPI_NOR_CMD_DUAL_OUTPUT_READ   0x3Bu /* Dual Output Fast Read */
#define SPI_NOR_CMD_QUAD_OUTPUT_READ   0x6Bu /* Quad Output Fast Read */
#define SPI_NOR_CMD_RDID               0x9Fu /* Read Identification (JEDEC ID) */
#define SPI_NOR_CMD_WREAR              0xC5u /* Write Extended Address Register */
#define SPI_NOR_CMD_RDEAR              0xC8u /* Read Extended Address Register */

#define SPI_NOR_SR1_WIP                0x01u /* Write/erase In Progress */
#define SPI_NOR_SR1_WEL                0x02u /* Write Enable Latch */
#define SPI_NOR_SR2_QE                 0x02u /* Quad Enable, bit S9 of SR2 */

/* These are response bytes, not opcodes. Manufacturer C8 != command RDEAR C8. */
#define GD25Q256E_JEDEC_MANUFACTURER   0xC8u
#define GD25Q256E_JEDEC_MEMORY_TYPE    0x40u
#define GD25Q256E_JEDEC_CAPACITY       0x19u

#endif
