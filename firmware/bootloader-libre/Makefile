SDCC ?= sdcc
SDAS ?= sdas8051
MAKEBIN ?= makebin
REPO_ROOT ?= ../..
PYTHON ?= $(REPO_ROOT)/.venv/bin/python
FW037 ?= $(REPO_ROOT)/MSI_MPG_341CQPX_QD-OLED_FW.037_0225.bin
FW034 ?= $(REPO_ROOT)/MSI_MPG_341CQPX_QD-OLED_FW.034_D728.bin
# Первые 64 КиБ банка 0 U4002 этого монитора: FW.034 плюс таблица слота 1 из
# reference/. Полный дамп тоже подходит: make verify FLASH=../../flash/u4002_a.bin
FLASH ?= $(BUILD)/u4002-bank0-64k.bin
HOST_CC ?= cc

BUILD := build
SRC := src
CODE_LIMIT := 0x2000
C_SOURCES := bootloader.c flash.c gpio.c recovery.c timing.c uart.c
C_OBJECTS := $(patsubst %.c,$(BUILD)/%.rel,$(C_SOURCES))
HEADERS := $(wildcard $(SRC)/*.h)
PLATFORM := ../platform/nt68503
HEADERS += $(wildcard $(PLATFORM)/*.h)

CFLAGS := -I$(PLATFORM) -mmcs51 --model-small --std-sdcc11 --opt-code-size \
	--no-xinit-opt --code-loc 0x0000 --code-size $(CODE_LIMIT) \
	--iram-size 0x100 --xram-loc 0x0000 --xram-size 0x10000
LDFLAGS := $(CFLAGS)

.PHONY: all clean verify references image test-gpio test-boot-abi

all: $(BUILD)/bootloader-a.bin

$(BUILD):
	mkdir -p $@

$(BUILD)/crt0.rel: $(SRC)/crt0.asm | $(BUILD)
	$(SDAS) -plosgff -o $@ $<

$(BUILD)/%.rel: $(SRC)/%.c $(HEADERS) | $(BUILD)
	$(SDCC) $(CFLAGS) -c -o $@ $<

$(BUILD)/bootloader.ihx: $(BUILD)/crt0.rel $(C_OBJECTS)
	$(SDCC) $(LDFLAGS) -o $@ $^

$(BUILD)/bootloader-a.bin: $(BUILD)/bootloader.ihx
	$(MAKEBIN) -s $(CODE_LIMIT) $< $@

$(BUILD)/test-gpio: tools/test_gpio.c $(SRC)/gpio.c $(HEADERS) | $(BUILD)
	$(HOST_CC) -I$(PLATFORM) -std=c99 -Wall -Wextra -Werror -pedantic -o $@ $<

test-gpio: $(BUILD)/test-gpio
	./$(BUILD)/test-gpio

$(BUILD)/test-boot-abi: tools/test_boot_abi.c $(SRC)/bootloader.c $(HEADERS) | $(BUILD)
	$(HOST_CC) -I$(PLATFORM) -std=c99 -Wall -Wextra -Werror -pedantic -o $@ $<

references:
	@for f in "$(FW037)" "$(FW034)"; do \
		test -f "$$f" || { echo "нет файла MSI $$f: см. README, раздел «Эталоны»" >&2; exit 2; }; \
	done

$(BUILD)/u4002-bank0-64k.bin: reference/u4002-slot1-table.txt tools/make_reference_flash.py | $(BUILD) references
	$(PYTHON) tools/make_reference_flash.py --fw034 "$(FW034)" --table $< --output $@

test-boot-abi: $(BUILD)/test-boot-abi $(FLASH) | references
	./$(BUILD)/test-boot-abi "$(FW037)" \
		"$(FW034)" "$(FLASH)"

verify: $(BUILD)/bootloader-a.bin test-gpio test-boot-abi
	$(PYTHON) tools/verify.py --binary $< \
		--source-dir $(SRC) \
		--fw037 "$(FW037)" \
		--fw034 "$(FW034)" \
		--flash "$(FLASH)"

# Создаёт новый файл и не меняет исходный образ. Заменяются только занятые
# сектора bootloader; JEDEC-таблица и обе таблицы разделов сохраняются.
image: verify
	@test -n "$(FW)" || (echo "usage: make image FW=../../firmware.bin" >&2; exit 2)
	$(PYTHON) tools/make_image.py --bootloader $(BUILD)/bootloader-a.bin \
		--firmware "$(FW)" --output $(BUILD)/firmware-libre.bin

clean:
	rm -rf $(BUILD)
