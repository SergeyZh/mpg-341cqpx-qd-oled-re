/* SPDX-License-Identifier: MIT
 * Minimal MMIO/SDK model for the actual usb.c scheduler regression.
 * It does not model USB electrical timing or control packet toggles. */
#ifndef MOCK_NUC1261_H
#define MOCK_NUC1261_H
#include <stdint.h>
#include <stddef.h>
#define EP0 0
#define EP1 1
#define EP2 2
#define EP3 3
#define EP4 4
#define EP5 5
#define BIT4 (1u<<4)
#define BIT5 (1u<<5)
#define USBD_IRQn 23
#define USBD_CFG_CSTALL 0
#define USBD_CFG_EPMODE_IN 0
#define USBD_CFG_EPMODE_OUT 0
#define USBD_INTSTS_FLDET (1u<<0)
#define USBD_INTSTS_BUS (1u<<1)
#define USBD_INTSTS_WAKEUP (1u<<2)
#define USBD_INTSTS_USB (1u<<3)
#define USBD_INTSTS_SETUP (1u<<4)
#define USBD_INTSTS_EP0 (1u<<5)
#define USBD_INTSTS_EP1 (1u<<6)
#define USBD_INTSTS_EP2 (1u<<7)
#define USBD_INTSTS_EP3 (1u<<8)
#define USBD_INTSTS_EP4 (1u<<9)
#define USBD_INTSTS_EP5 (1u<<10)
#define USBD_STATE_USBRST 1u
#define USBD_STATE_SUSPEND 2u
#define USBD_STATE_RESUME 4u
#define USBD_EPSTS_EPSTS1_Msk 2u
typedef struct { uint32_t STBUFSEG,EPSTS; } MOCK_USBD;
typedef struct {
    const uint8_t *device, *gu8ConfigDesc;
    const uint8_t **strings, **reports;
    const uint32_t *lengths, *offsets;
    const void *extra;
} S_USBD_INFO_T;
extern MOCK_USBD mock_usbd;
extern uint8_t mock_buffer[512];
extern unsigned mock_offsets[6],mock_lengths[6],mock_flags,mock_state;
extern uint32_t SystemCoreClock,mock_systick_ticks;
#define USBD (&mock_usbd)
#define USBD_BUF_BASE ((uintptr_t)mock_buffer)
#define USBD_GET_EP_BUF_ADDR(ep) mock_offsets[ep]
#define USBD_SET_EP_BUF_ADDR(ep,n) (mock_offsets[ep]=(n))
#define USBD_GET_PAYLOAD_LEN(ep) mock_lengths[ep]
void mock_payload(unsigned ep,unsigned n);
#define USBD_SET_PAYLOAD_LEN(ep,n) mock_payload(ep,n)
#define USBD_CONFIG_EP(ep,n) ((void)(ep),(void)(n))
#define USBD_SET_EP_STALL(ep) ((void)(ep))
#define USBD_SET_DATA1(ep) ((void)(ep))
#define USBD_SET_DATA0(ep) ((void)(ep))
#define USBD_STOP_TRANSACTION(ep) ((void)(ep))
#define USBD_GET_INT_FLAG() mock_flags
#define USBD_GET_BUS_STATE() mock_state
#define USBD_CLR_INT_FLAG(n) (mock_flags &= ~(n))
#define USBD_IS_ATTACHED() 1
#define USBD_ENABLE_USB() ((void)0)
#define USBD_DISABLE_USB() ((void)0)
#define USBD_DISABLE_PHY() ((void)0)
#define __get_PRIMASK() 0u
#define __disable_irq() ((void)0)
#define __set_PRIMASK(n) ((void)(n))
#define __DMB() ((void)0)
void NVIC_EnableIRQ(int irq);
void NVIC_DisableIRQ(int irq);
uint32_t SysTick_Config(uint32_t ticks);
void USBD_Open(S_USBD_INFO_T *info,void (*class_request)(void),void *vendor_request);
void USBD_Start(void);
void USBD_SetConfigCallback(void (*callback)(void));
void USBD_GetSetupPacket(uint8_t *setup);
void USBD_PrepareCtrlIn(uint8_t *data,uint32_t n);
void USBD_PrepareCtrlOut(uint8_t *data,uint32_t n);
void USBD_ProcessSetupPacket(void);
void USBD_CtrlIn(void);
void USBD_CtrlOut(void);
void USBD_SwReset(void);
void USBD_LockEpStall(uint32_t mask);
#endif
