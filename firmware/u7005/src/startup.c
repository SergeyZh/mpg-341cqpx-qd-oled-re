/* SPDX-License-Identifier: MIT */
#include <stdint.h>
extern uint32_t _stack_top, _data_load, _data_start, _data_end, _bss_start, _bss_end;
extern uint8_t _code_end;
/* Fixed descriptor at 0xC0: host rejects images without metadata normalization. */
__attribute__((section(".image_info"),used))
const struct { char magic[4]; uint32_t version; const void *end; uint32_t flags; }
    image_info={{'U','7','B','I'},1,&_code_end,1};
extern int main(void);
static void fault(void) { for(;;) __asm volatile("nop"); }
void Reset_Handler(void) {
    uint32_t *s=&_data_load;
    for(uint32_t *p=&_data_start;p<&_data_end;) *p++=*s++;
    for(uint32_t *p=&_bss_start;p<&_bss_end;) *p++=0;
    main(); fault();
}
extern void SysTick_Handler(void), UART02_IRQHandler(void), UART1_IRQHandler(void);
extern void USBD_IRQHandler(void), GPAB_IRQHandler(void);
typedef void (*vector)(void);
__attribute__((section(".vectors"),used))
const vector vectors[48]={
    (vector)&_stack_top,Reset_Handler,fault,fault,0,0,0,0,0,0,0,fault,0,0,fault,SysTick_Handler,
    fault,fault,fault,fault,GPAB_IRQHandler,fault,fault,fault,
    fault,fault,fault,fault,UART02_IRQHandler,UART1_IRQHandler,fault,fault,
    0,0,fault,fault,0,0,fault,USBD_IRQHandler,fault,fault,fault,0,fault,fault,fault,fault
};
