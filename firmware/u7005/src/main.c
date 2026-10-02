/* SPDX-License-Identifier: MIT */
#include "NUC1261.h"
#include "board.h"
struct bridge bridge;
int main(void) {
    board_init();
    if(!board_prepare_image()) board_io.enter_ldrom();
    bridge_init(&bridge,&board_io); usb_init(bridge.usb_mode);
    for(;;) { usb_poll(); board_poll(); __WFI(); }
}
