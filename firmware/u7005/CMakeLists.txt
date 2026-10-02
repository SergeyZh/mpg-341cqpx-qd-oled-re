cmake_minimum_required(VERSION 3.20)
set(CMAKE_SYSTEM_NAME Generic)
set(CMAKE_SYSTEM_PROCESSOR arm)
set(CMAKE_C_COMPILER arm-none-eabi-gcc)
set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)
project(u7005 C)
set(CMAKE_C_STANDARD 11)
set(BSP "$ENV{U7005_BSP}" CACHE PATH "NUC1261 BSP")
if(NOT EXISTS "${BSP}/Library/StdDriver/src/usbd.c")
  message(FATAL_ERROR "Set U7005_BSP; use tools/u7005-env.sh")
endif()
set(DRIVER "${BSP}/Library/StdDriver")
set(DEVICE "${BSP}/Library/Device/Nuvoton/NUC1261")
add_library(nuvoton OBJECT ${DRIVER}/src/clk.c ${DRIVER}/src/uart.c ${DRIVER}/src/i2c.c
  ${DRIVER}/src/usbd.c ${DEVICE}/Source/system_NUC1261.c)
target_include_directories(nuvoton PUBLIC ${DRIVER}/inc ${DEVICE}/Include ${BSP}/Library/CMSIS/Include)
target_compile_options(nuvoton PRIVATE -mcpu=cortex-m0 -mthumb -Os -ffunction-sections -fdata-sections)
add_executable(u7005.elf src/startup.c src/main.c src/board.c src/usb.c src/bridge.c src/msc.c src/boot_metadata.c)
target_link_libraries(u7005.elf PRIVATE nuvoton)
target_include_directories(u7005.elf PRIVATE include)
target_compile_options(u7005.elf PRIVATE -mcpu=cortex-m0 -mthumb -Os -g3 -Wall -Wextra -Werror
  -ffunction-sections -fdata-sections -fno-common -fstack-usage)
target_link_options(u7005.elf PRIVATE -mcpu=cortex-m0 -mthumb -nostartfiles --specs=nano.specs
  --specs=nosys.specs -T${CMAKE_CURRENT_SOURCE_DIR}/linker.ld
  -Wl,--gc-sections,-Map=${CMAKE_CURRENT_BINARY_DIR}/u7005.map,--print-memory-usage)
set_property(TARGET u7005.elf APPEND PROPERTY LINK_DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/linker.ld)
add_custom_command(TARGET u7005.elf POST_BUILD
  COMMAND arm-none-eabi-objcopy -O binary $<TARGET_FILE:u7005.elf> ${CMAKE_CURRENT_BINARY_DIR}/u7005-code.bin
  COMMAND arm-none-eabi-size $<TARGET_FILE:u7005.elf>)
