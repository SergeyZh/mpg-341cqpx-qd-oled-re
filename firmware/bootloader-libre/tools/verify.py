#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Static checks for the libre bootloader and its shared-structure ABI."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


FLASH_IMAGE_SIZE = 0x2000
SHARE_SIZE = 0x9A
VENDOR_STRINGS = (
    b"STBC Boot Loader",
    b"Can't find valid partition table",
    b"Re-booting STBC code",
    b"SetExtendedAddr",
    b"Set Flash to Quad mode",
    b"Set Flash to Dual mode",
    b"System can not support Dual mode",
)
UART_INIT_SEQUENCE = bytes.fromhex(
    "bf 20 04 "       # CJNE R7,#0x20: select the pre-main clock variant
    "7f cc 80 02 "    # D511=0x20: TH1 reload is -52
    "7f 98 "          # installed D511=0x17: TH1 reload is -104
    "8f 8d "          # MOV TH1,R7
    "75 98 52 "       # MOV SCON,#0x52 (mode 1 and initial TI=1)
    "75 89 21 "       # MOV TMOD,#0x21 (timer 1 mode 2)
    "75 87 80 "       # MOV PCON,#0x80 (SMOD=1)
    "d2 8e"           # SETB TR1
)
UART_FLOW_CONTROL_SEQUENCE = bytes.fromhex(
    "30 98 11 "       # JNB RI: no received byte
    "74 13 "          # MOV A,#XOFF
    "b5 99 0c "       # ignore anything except XOFF
    "c2 98 "          # consume XOFF
    "30 98 fd "       # wait for the next received byte
    "ae 99 "          # read SBUF
    "c2 98 "          # consume it
    "be 11 f6"        # wait until that byte is XON
)
UART_TX_SEQUENCE = bytes.fromhex(
    "10 99 02 "       # JBC TI,+2: wait for completion and clear TI atomically
    "80 fb "          # retry while TI=0
    "8f 99 "          # MOV SBUF,R7
    "22"              # RET
)
VENDOR_STARTUP_TABLE = bytes.fromhex(
    "06 08 0c 18 20 30 40 60 "  # IDATA[08..0d]
    "06 0e 0c 18 20 30 3c 44 "  # IDATA[0e..13]
    "01 14 00 "                 # IDATA[14]
    "00"                        # terminator
)
VENDOR_STARTUP_TABLE_OFFSET = 0x185F
UART_DRAIN_SEQUENCE = bytes.fromhex(
    "30 99 fd "       # JNB TI,-3: wait for the final byte before F1D
    "22"              # RET
)
ADC_INIT_SEQUENCE = bytes.fromhex(
    "90 f3 c0 e4 f0 "              # ADC control 0 = 0
    "a3 a3 74 80 f0 "              # ADC control 2 = 0x80
    "a3 23 f0 "                    # ADC control 3 = 1
    "90 f0 80 e0 44 01 f0 "        # enable channel 5, preserve other bits
    "90 f3 c1 74 1b f0 22"         # start conversion and return
)
JOYSTICK_DECODE_SEQUENCE = bytes.fromhex(
    "24 db fd bd 2d 00 50 04 7e 01 "     # 0x25..0x51 -> direction 1
    "80 25 ef 24 a0 fd bd 25 00 50 04 7e 02 "
    "80 18 ef 24 6d fd bd 1d 00 50 04 7e 03 "
    "80 0b ef 24 43 fd bd 17 00 50 02 7e 04"  # 0xBD..0xD3 -> direction 4
)
JOYSTICK_TEXT = b"libre: joystick direction "
RECOVERY_DELAY_SEQUENCE = bytes.fromhex(
    "af 82 7e ff 7d ff dd fe de fa df f6 22"
)
FLASH_POLL_DELAY_PATTERN = re.compile(
    # MOV direct,#10; MOV A,direct; JZ +4; DEC direct; SJMP -8; RET.
    # The linker may relocate the overlay counter; all three operands must
    # name the same lower-IRAM byte, never an SFR or a bank-0 register.
    rb"\x75([\x08-\x7f])\x0a\xe5\1\x60\x04\x15\1\x80\xf8\x22"
)
RECOVERY_RAW_I2C_SEQUENCE = bytes.fromhex(
    "90 f0 6e e0 54 7f f0 "       # disable service UART 4
    "90 f0 72 74 f0 f0 "
    "90 f0 30 e0 54 bf f0 "       # release its pin pair
    "90 f0 1c e0 54 7f f0 "       # reset/disable old slave channel
    "90 f1 81 e0 54 7f f0 "
    "90 f0 48 74 6f f0 "          # channel 1 address 0x6E + enable
    "90 f0 45 74 ff f0 "
    "90 f0 43 74 f8 f0 "
    "90 f0 41 e0 44 40 f0 22"     # arm channel 1 and return
)
RECOVERY_TEXT = b"libre: ISP ready\r\n"
RECOVERY_GPIO_TEXT = b"libre: gpio"
COLD_USB_GPIO_TABLE = bytes.fromhex(
    "04 50 af 0c "
    "06 83 7c 74 "
    "07 70 8e c2 "
    "05 10 ff 2f "
    "0d 31 de 42"
)
USB_MODE_GPIO_TABLE = bytes.fromhex(
    "03 04 f3 fb "
    "0a e3 1c e4"
)
REQUIRED_C_MODULES = {
    "bootloader.c", "flash.c", "gpio.c", "recovery.c", "timing.c", "uart.c",
}
RECOVERY_SOURCE_STEPS = (
    "apply_cold_usb_gpio_table();",
    "delay_recovery_periods(GPIO_SETTLE_PERIODS);",
    "enable_vl211_and_u7005();",
    "select_usb_b_and_reset_vl211();",
    "enable_raw_service_i2c();",
)
RECOVERY_GPIO_NAMES = (
    "GPIO_VL211_ENABLE",
    "GPIO_U7005_ENABLE",
    "GPIO_VL211_USB_B_SELECT",
    "GPIO_VL211_RESET",
    "GPIO_USB_INIT_BANK6_BIT7",
    "GPIO_USB_INIT_BANK7_BIT0",
    "GPIO_USB_INIT_BANK5_BIT4",
    "GPIO_ACTIVE_BANK4_BIT7",
    "GPIO_ACTIVE_BANK13_BIT0",
)


def shared_structure(table: bytes) -> bytes:
    if len(table) < 13 * 8:
        raise ValueError("partition table is shorter than 13 records")
    out = bytearray(SHARE_SIZE)
    out[:2] = b"\x00\x01"
    out[0x02:0x0A] = table[0x08:0x10]
    out[0x0E:0x16] = table[0x10:0x18]
    out[0x16:0x1A] = table[0x18:0x1C]
    out[0x1A:0x1E] = bytes.fromhex("9f 06 00 00")
    out[0x1E:0x22] = table[0x1C:0x20]
    out[0x22:0x26] = table[0x20:0x24]
    out[0x32:0x3A] = table[0x28:0x30]
    out[0x3A:0x3E] = table[0x30:0x34]
    out[0x3E:0x42] = bytes.fromhex("9f 19 60 00")
    out[0x42:0x46] = table[0x34:0x38]
    out[0x46:0x4E] = table[0x40:0x48]
    out[0x54:0x56] = bytes.fromhex("07 ff")
    out[0x5A:0x62] = table[0x38:0x40]
    out[0x66:0x6A] = bytes.fromhex("87 20 05 00")
    for record in range(9, 13):
        destination = 0x6A + (record - 9) * 12
        source = record * 8
        out[destination:destination + 8] = table[source:source + 8]
    return bytes(out)


def check_table(image: bytes, offset: int, expected_hex: str) -> None:
    actual = shared_structure(image[offset:offset + 13 * 8])
    expected = bytes.fromhex(expected_hex)
    if actual != expected:
        raise AssertionError(
            f"shared structure mismatch for table at {offset:#x}:\n"
            f"actual   {actual.hex(' ')}\n"
            f"expected {expected.hex(' ')}"
        )


def check_c_sources(source_dir: Path) -> None:
    modules = {path.name for path in source_dir.glob("*.c")}
    if modules != REQUIRED_C_MODULES:
        raise AssertionError(
            f"unexpected C module set: {sorted(modules)}; "
            f"expected {sorted(REQUIRED_C_MODULES)}"
        )

    for path in source_dir.glob("*.c"):
        source = path.read_text()
        for forbidden in ("__asm", "__endasm", "__naked"):
            if forbidden in source:
                raise AssertionError(f"{path}: inline assembly token {forbidden!r}")

    recovery = (source_dir / "recovery.c").read_text()
    gpio = (source_dir / "gpio.c").read_text()
    cursor = 0
    for step in RECOVERY_SOURCE_STEPS:
        cursor = recovery.find(step, cursor)
        if cursor < 0:
            raise AssertionError(f"recovery C phase is absent or reordered: {step}")
        cursor += len(step)

    if "REG_GPIO" in recovery:
        raise AssertionError("recovery bypasses the pin-level GPIO API")
    for name in RECOVERY_GPIO_NAMES:
        if name not in recovery:
            raise AssertionError(f"named recovery GPIO is absent: {name}")
    if "void gpio_configure(gpio_pin_t gpio, enum gpio_action action)" not in gpio:
        raise AssertionError("pin/action GPIO configuration API is absent")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--fw037", type=Path, required=True)
    parser.add_argument("--fw034", type=Path, required=True)
    parser.add_argument("--flash", type=Path, required=True)
    args = parser.parse_args()

    check_c_sources(args.source_dir)
    binary = args.binary.read_bytes()
    if len(binary) != FLASH_IMAGE_SIZE:
        raise AssertionError(
            f"binary length is {len(binary):#x}, expected {FLASH_IMAGE_SIZE:#x}"
        )
    if binary[:3] != bytes.fromhex("02 00 30"):
        raise AssertionError("reset vector is not LJMP 0x0030")
    for text in VENDOR_STRINGS:
        if text in binary:
            raise AssertionError(f"vendor diagnostic string present: {text!r}")
    if UART_INIT_SEQUENCE not in binary:
        raise AssertionError("expected variant-aware 4800-baud UART init is absent")
    if UART_FLOW_CONTROL_SEQUENCE not in binary:
        raise AssertionError("expected UART XOFF/XON flow control is absent")
    if UART_TX_SEQUENCE not in binary:
        raise AssertionError("expected TI wait and SBUF transmit sequence is absent")
    if UART_DRAIN_SEQUENCE not in binary:
        raise AssertionError("expected final UART drain before F1D is absent")
    if ADC_INIT_SEQUENCE not in binary:
        raise AssertionError("expected joystick ADC channel-5 setup is absent")
    if JOYSTICK_DECODE_SEQUENCE not in binary:
        raise AssertionError("expected four joystick ADC ranges are absent")
    if JOYSTICK_TEXT not in binary:
        raise AssertionError("expected libre joystick UART text is absent")
    if binary.count(RECOVERY_DELAY_SEQUENCE) != 1:
        raise AssertionError("expected pure-C nested recovery delay is absent")
    if len(list(FLASH_POLL_DELAY_PATTERN.finditer(binary))) != 1:
        raise AssertionError("expected pure-C flash polling delay is absent")
    if binary.count(RECOVERY_RAW_I2C_SEQUENCE) != 1:
        raise AssertionError("expected raw service-I2C recovery setup is absent")
    if binary.count(COLD_USB_GPIO_TABLE) != 1:
        raise AssertionError("expected cold USB GPIO bank table is absent")
    if binary.count(USB_MODE_GPIO_TABLE) != 1:
        raise AssertionError("expected USB-B/reset GPIO bank table is absent")
    if binary.count(RECOVERY_TEXT) != 1:
        raise AssertionError("expected libre ISP recovery UART text is absent")
    if binary.count(RECOVERY_GPIO_TEXT) != 1:
        raise AssertionError("expected recovery GPIO read-back text is absent")

    adc_init_address = binary.index(ADC_INIT_SEQUENCE)
    adc_read_address = binary.index(bytes.fromhex("90 f3 c9"))
    init_call = bytes((0x12, adc_init_address >> 8, adc_init_address & 0xFF))
    read_call = bytes((0x12, adc_read_address >> 8, adc_read_address & 0xFF))
    banner_address = binary.index(b"\r\nbootloader-libre: start\r\n")
    banner_reference = bytes((0x90, banner_address >> 8, banner_address & 0xFF))
    init_call_at = binary.index(init_call)
    banner_ref_at = binary.index(banner_reference)
    read_call_at = binary.index(read_call)
    if not init_call_at < banner_ref_at < read_call_at <= banner_ref_at + 16:
        raise AssertionError("joystick ADC is not initialized before the settling banner/read")

    # Keep the sampled direction in R7 for later table selection. SDCC saves
    # it around calls; CJNE skips PUSH + LCALL + POP on the non-recovery path.
    branch_prefix = read_call + bytes.fromhex("af 82 bf 01 07 c0 07 12")
    if binary[read_call_at:read_call_at + len(branch_prefix)] != branch_prefix:
        raise AssertionError("recovery call is not conditioned on joystick direction 1")
    recovery_call_at = read_call_at + len(read_call) + 7
    recovery_entry = int.from_bytes(binary[recovery_call_at + 1:recovery_call_at + 3],
                                    "big")
    recovery_text_address = binary.index(RECOVERY_TEXT)
    recovery_text_reference = bytes((0x90, recovery_text_address >> 8,
                                     recovery_text_address & 0xFF))
    if recovery_text_reference not in binary[recovery_entry:recovery_entry + 64]:
        raise AssertionError("direction-1 branch does not enter the ISP recovery function")
    flash_init_address = binary.index(bytes.fromhex("90 f1 df 74 80 f0"))
    flash_init_call = bytes((0x12, flash_init_address >> 8, flash_init_address & 0xFF))
    normal_init = bytes.fromhex("d0 07 c0 07") + flash_init_call
    if binary[recovery_call_at + 3:recovery_call_at + 3 + len(normal_init)] != normal_init:
        raise AssertionError("normal flash initialization does not follow recovery selection")

    drain_address = binary.index(UART_DRAIN_SEQUENCE)
    drain_call = bytes((0x12, drain_address >> 8, drain_address & 0xFF))
    boot_control = bytes.fromhex("90 f1 d0")  # MOV DPTR,#REG_BOOT_CTRL
    if binary.count(boot_control) != 1:
        raise AssertionError("expected exactly one REG_BOOT_CTRL write site")
    boot_control_at = binary.index(boot_control)
    if drain_call not in binary[max(0, boot_control_at - 32):boot_control_at]:
        raise AssertionError("UART drain is not called immediately before F1D")
    if binary[-32:] != b"\xff" * 32:
        raise AssertionError("code reaches the end of the two-sector flash image")

    fw037 = args.fw037.read_bytes()
    fw034 = args.fw034.read_bytes()
    flash = args.flash.read_bytes()
    for name, image in (("FW.037", fw037), ("FW.034", fw034)):
        actual = image[
            VENDOR_STARTUP_TABLE_OFFSET:
            VENDOR_STARTUP_TABLE_OFFSET + len(VENDOR_STARTUP_TABLE)
        ]
        if actual != VENDOR_STARTUP_TABLE:
            raise AssertionError(f"{name} vendor startup table changed: {actual.hex(' ')}")
    check_table(
        fw037,
        0x6000,
        "00 01 00 02 00 00 00 00 e5 52 00 00 00 00 00 0d "
        "00 00 00 00 80 c8 00 0e c0 00 9f 06 00 00 00 00 "
        "5a a0 00 10 80 00 00 00 00 00 00 00 00 00 00 00 "
        "00 00 00 05 00 00 00 05 55 40 00 0a 60 00 9f 19 "
        "60 00 00 00 27 e8 00 0b 00 00 00 01 f4 c0 00 00 "
        "00 00 00 00 07 ff 00 00 00 00 00 03 00 00 00 00 "
        "d8 dc 00 00 00 00 87 20 05 00 00 00 00 00 00 00 "
        "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
        "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
        "00 00 00 00 00 00 00 00 00 00",
    )
    check_table(
        fw034,
        0x6000,
        "00 01 00 02 00 00 00 00 e5 52 00 00 00 00 00 0d "
        "00 00 00 00 7b 3c 00 0e c0 00 9f 06 00 00 00 00 "
        "5a 90 00 10 80 00 00 00 00 00 00 00 00 00 00 00 "
        "00 00 00 05 00 00 00 05 55 30 00 0a 60 00 9f 19 "
        "60 00 00 00 27 e8 00 0b 00 00 00 01 f3 b0 00 00 "
        "00 00 00 00 07 ff 00 00 00 00 00 03 00 00 00 00 "
        "d7 dc 00 00 00 00 87 20 05 00 00 00 00 00 00 00 "
        "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
        "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
        "00 00 00 00 00 00 00 00 00 00",
    )
    check_table(
        flash,
        0x7000,
        "00 01 01 02 00 00 00 00 e5 52 00 00 00 00 01 0d "
        "00 00 00 00 7b 3c 01 0e c0 00 9f 06 00 00 00 00 "
        "5a 68 01 10 80 00 00 00 00 00 00 00 00 00 00 00 "
        "00 00 01 05 00 00 00 05 55 70 01 0a 60 00 9f 19 "
        "60 00 00 00 14 a8 01 0b 00 00 00 01 f1 3d 00 00 "
        "00 00 00 00 07 ff 00 00 00 00 01 03 00 00 00 00 "
        "fc 38 00 00 00 00 87 20 05 00 00 00 00 00 00 00 "
        "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
        "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
        "00 00 00 00 00 00 00 00 00 00",
    )
    print(
        "verified: reset vector, code boundary, vendor startup constants, 4800-baud "
        "UART with XON/XOFF and final drain, joystick ADC, named GPIO and pure-C "
        "modular USB recovery setup, UART strings, "
        "FW.034/FW.037/slot-1 ABI"
    )


if __name__ == "__main__":
    main()
