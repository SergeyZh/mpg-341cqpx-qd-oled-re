/* SPDX-License-Identifier: MIT */
#include "NUC1261.h"
#include "board.h"
#include <assert.h>
#include <string.h>

MOCK_USBD mock_usbd;
uint8_t mock_buffer[512];
unsigned mock_offsets[6],mock_lengths[6],mock_flags,mock_state;
uint32_t SystemCoreClock=48000000,mock_systick_ticks;
struct bridge bridge;
static unsigned starts,in_packets;
static uint8_t sent[64];
static void (*configure)(void);
void USBD_IRQHandler(void);

void mock_payload(unsigned ep,unsigned n) {
    mock_lengths[ep]=n;
    if(ep==EP2 && n==64) {
        memcpy(sent,mock_buffer+mock_offsets[EP2],64); ++in_packets;
    }
}
void NVIC_EnableIRQ(int irq) { (void)irq; }
void NVIC_DisableIRQ(int irq) { (void)irq; }
uint32_t SysTick_Config(uint32_t ticks) { mock_systick_ticks=ticks; return 0; }
void USBD_Open(S_USBD_INFO_T *info,void (*callback)(void),void *vendor) {
    (void)info; (void)callback; (void)vendor;
}
void USBD_Start(void) {
    /* Pinned Nuvoton usbd.c:109 -> clk.h:430-440. The SDK borrows
     * SysTick for 100 ms and finishes with CTRL=0, without restoring it. */
    mock_systick_ticks=0; ++starts;
}
void USBD_SetConfigCallback(void (*callback)(void)) { configure=callback; }
void USBD_GetSetupPacket(uint8_t *s) { memset(s,0,8); s[2]=1; }
void USBD_PrepareCtrlIn(uint8_t *p,uint32_t n) { (void)p; (void)n; }
void USBD_PrepareCtrlOut(uint8_t *p,uint32_t n) { (void)p; (void)n; }
void USBD_ProcessSetupPacket(void) {}
void USBD_CtrlIn(void) {}
void USBD_CtrlOut(void) {}
void USBD_SwReset(void) {}
void USBD_LockEpStall(uint32_t mask) { (void)mask; }
void board_delay(uint32_t ms) { (void)ms; assert(mock_systick_ticks==48000); }
void msc_reset(void) {}
void msc_out(const uint8_t *p,size_t n) { (void)p; (void)n; }
size_t msc_in(uint8_t *p) { (void)p; return 0; }
bool msc_in_pending(void) { return false; }
bool msc_halted(void) { return false; }
void bridge_reset_transport(struct bridge *b) { (void)b; }
void bridge_report(struct bridge *b,const uint8_t *p,size_t n) {
    (void)b; assert(n==64); assert(usb_send(p));
}
static void tick_after_wfi(void) {
    /* Main sleeps after usb_poll/board_poll. No additional USB interrupt:
     * only a running periodic tick can cause the next iteration here. */
    if(mock_systick_ticks) usb_poll();
}
static void receive_report(uint8_t command) {
    unsigned before=in_packets;
    memset(mock_buffer+mock_offsets[EP3],0,64);
    mock_buffer[mock_offsets[EP3]]=1;
    mock_buffer[mock_offsets[EP3]+1]=command;
    mock_lengths[EP3]=64;
    mock_flags=USBD_INTSTS_USB|USBD_INTSTS_EP3; USBD_IRQHandler();
    usb_poll(); tick_after_wfi();
    assert(in_packets==before+1);
    assert(sent[0]==1 && sent[1]==command);
    mock_flags=USBD_INTSTS_USB|USBD_INTSTS_EP2; USBD_IRQHandler();
}
int main(int argc,char **argv) {
    (void)argv;
    mock_systick_ticks=48000; /* board_init has already enabled it. */
    usb_init(0); configure();
    if(argc>1) {
        usb_request_mode(1); usb_poll(); configure();
        assert(starts==2);
    } else assert(starts==1);
    receive_report(0xb0); receive_report(0xb2); receive_report(0xb4);
    assert(mock_systick_ticks==48000);
    return 0;
}
