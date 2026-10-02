/* SPDX-License-Identifier: MIT
 * NUC1261 USBD peripheral via the Apache-2.0 Nuvoton StdDriver.
 */
#include "NUC1261.h"
#include "board.h"
#include <string.h>

#define Q 8u
static uint8_t rx[Q][64],tx[Q][64],last_report[4][64],control_out[64];
static uint8_t control_in[64];
static volatile unsigned rh,rt,th,tt;
static volatile bool in_busy,out_armed,reset_pending,control_pending;
static unsigned control_count;
static uint32_t control_toggle;
static volatile bool configured,msc_reset_pending;
static uint8_t idle_rate,protocol,mode;
static volatile bool mode_pending;
static uint8_t requested_mode;
static volatile bool bulk_ready,bulk_busy;
static uint8_t bulk_out[64];
static volatile size_t bulk_length;
static const uint8_t device[]={18,1,0x10,1,0,0,0,8,0x62,0x14,0xa4,0x3f,0,0,1,2,3,1};
#define REPORT(N) 0x85,N,0x15,0,0x25,0xff,0x19,1,0x29,8,0x95,63,0x75,8,0x81,2,0x19,1,0x29,8,0x91,2
static const uint8_t reports[]={5,1,9,0,0xa1,1,REPORT(1),REPORT(2),REPORT(3),REPORT(4),0xc0};
#define HID_INTERFACE 9,4,0,0,2,3,0,0,0,9,0x21,0x10,1,0,1,0x22,95,0,7,5,0x81,3,64,0,1,7,5,2,3,64,0,1
static const uint8_t hid_config[]={9,2,41,0,1,1,0,0x80,50,HID_INTERFACE};
static const uint8_t composite_config[]={9,2,64,0,2,1,0,0x80,50,HID_INTERFACE,
    9,4,1,0,2,8,6,0x50,0,7,5,0x83,2,64,0,0,7,5,4,2,64,0,0};
static const uint8_t lang[]={4,3,9,4};
/* Preserve the descriptor as transmitted by MSI (bLength=6 spells "MS"). */
static const uint8_t vendor[]={6,3,'M',0,'S',0,'I',0};
static const uint8_t product[]={44,3,'M',0,'S',0,'I',0,' ',0,'G',0,'a',0,'m',0,'i',0,'n',0,'g',0,
    ' ',0,'C',0,'o',0,'n',0,'t',0,'r',0,'o',0,'l',0,'l',0,'e',0,'r',0};
static const uint8_t serial[]={26,3,'A',0,'0',0,'2',0,'0',0,'1',0,'9',0,'0',0,'1',0,'0',0,'7',0,'0',0,'0',0};
static const uint8_t *strings[]={lang,vendor,product,serial};
static const uint8_t *report_list[]={reports,0,0};
static const uint32_t report_lengths[]={sizeof(reports),0,0},hid_offsets[]={18,0,0};
static S_USBD_INFO_T info={device,hid_config,strings,report_list,report_lengths,hid_offsets,0};

static void copy_from_ep(unsigned ep,uint8_t *p,size_t n) {
    volatile uint8_t *source=(volatile uint8_t *)(USBD_BUF_BASE+USBD_GET_EP_BUF_ADDR(ep));
    for(size_t j=0;j<n;j++) p[j]=source[j];
}
static void copy_to_ep(unsigned ep,const uint8_t *p,size_t n) {
    volatile uint8_t *target=(volatile uint8_t *)(USBD_BUF_BASE+USBD_GET_EP_BUF_ADDR(ep));
    for(size_t j=0;j<n;j++) target[j]=p[j];
}
static void endpoints(void) {
    USBD->STBUFSEG=0;
    USBD_CONFIG_EP(EP0,USBD_CFG_CSTALL|USBD_CFG_EPMODE_IN); USBD_SET_EP_BUF_ADDR(EP0,8);
    USBD_CONFIG_EP(EP1,USBD_CFG_CSTALL|USBD_CFG_EPMODE_OUT); USBD_SET_EP_BUF_ADDR(EP1,8);
    USBD_CONFIG_EP(EP2,USBD_CFG_EPMODE_IN|1); USBD_SET_EP_BUF_ADDR(EP2,16);
    USBD_CONFIG_EP(EP3,USBD_CFG_EPMODE_OUT|2); USBD_SET_EP_BUF_ADDR(EP3,80);
    USBD_SET_PAYLOAD_LEN(EP3,64); out_armed=true;
    if(mode) {
        USBD_CONFIG_EP(EP4,USBD_CFG_EPMODE_IN|3); USBD_SET_EP_BUF_ADDR(EP4,144);
        USBD_CONFIG_EP(EP5,USBD_CFG_EPMODE_OUT|4); USBD_SET_EP_BUF_ADDR(EP5,208);
        USBD_SET_PAYLOAD_LEN(EP5,64);
    } else { USBD_CONFIG_EP(EP4,0); USBD_CONFIG_EP(EP5,0); }
}
static void stall_control(void) { USBD_SET_EP_STALL(EP0); USBD_SET_EP_STALL(EP1); }
static void ctrl_in(const uint8_t *p,size_t n) {
    USBD_SET_DATA1(EP0); USBD_PrepareCtrlIn((uint8_t *)p,(uint32_t)n); USBD_PrepareCtrlOut(0,0);
}
static void ctrl_ack(void) { USBD_SET_DATA1(EP0); USBD_SET_PAYLOAD_LEN(EP0,0); }
static void class_request(void) {
    uint8_t s[8]; USBD_GetSetupPacket(s);
    uint16_t n=(uint16_t)(s[6]|s[7]<<8),value=(uint16_t)(s[2]|s[3]<<8);
    if(s[4]==0 && s[5]==0) {
        if(s[0]==0xa1) {
            if(s[1]==2 && n==1) { ctrl_in(&idle_rate,1); return; }
            if(s[1]==3 && n==1) { ctrl_in(&protocol,1); return; }
            if(s[1]==1 && n<=64 && s[3]==1 && s[2]>=1 && s[2]<=4) {
                memcpy(control_in,last_report[s[2]-1],n); ctrl_in(control_in,n); return;
            }
        } else if(s[0]==0x21) {
            if(s[1]==10 && n==0) { idle_rate=s[3]; ctrl_ack(); return; }
            if(s[1]==11 && n==0 && value<=1) { protocol=s[2]; ctrl_ack(); return; }
            if(s[1]==9 && n==64 && s[3]==2 && s[2]>=1 && s[2]<=4 && rh-rt<Q-1) {
                memset(control_out,0,64); control_pending=true;
                control_count=0; control_toggle=0;
                USBD_SET_DATA1(EP1); USBD_PrepareCtrlOut(control_out,64); ctrl_ack(); return;
            }
        }
    } else if(mode && s[4]==1 && s[5]==0 && value==0) {
        static uint8_t lun;
        if(s[0]==0xa1 && s[1]==0xfe && n==1) { ctrl_in(&lun,1); return; }
        if(s[0]==0x21 && s[1]==0xff && n==0) {
            msc_reset_pending=true; bulk_ready=bulk_busy=false;
            USBD_LockEpStall(0);
            USBD_SET_DATA0(EP4); USBD_SET_DATA0(EP5); USBD_SET_PAYLOAD_LEN(EP5,64);
            ctrl_ack(); return;
        }
    }
    stall_control();
}
void USBD_IRQHandler(void) {
    uint32_t flags=USBD_GET_INT_FLAG(),state=USBD_GET_BUS_STATE();
    if(flags & USBD_INTSTS_FLDET) {
        USBD_CLR_INT_FLAG(USBD_INTSTS_FLDET);
        if(USBD_IS_ATTACHED()) USBD_ENABLE_USB();
        else { USBD_DISABLE_USB(); reset_pending=true; }
    }
    if(flags & USBD_INTSTS_BUS) {
        USBD_CLR_INT_FLAG(USBD_INTSTS_BUS);
        if(state & USBD_STATE_USBRST) {
            USBD_ENABLE_USB(); USBD_SwReset();
            USBD_LockEpStall(0);
            rh=rt=th=tt=0; in_busy=false; control_pending=false; configured=false;
            bulk_busy=bulk_ready=false; reset_pending=true; endpoints();
        }
        if(state & USBD_STATE_SUSPEND) USBD_DISABLE_PHY();
        if(state & USBD_STATE_RESUME) USBD_ENABLE_USB();
    }
    if(flags & USBD_INTSTS_WAKEUP) USBD_CLR_INT_FLAG(USBD_INTSTS_WAKEUP);
    if(flags & USBD_INTSTS_USB) {
        if(flags & USBD_INTSTS_SETUP) {
            USBD_CLR_INT_FLAG(USBD_INTSTS_SETUP); control_pending=false;
            USBD_STOP_TRANSACTION(EP0); USBD_STOP_TRANSACTION(EP1); USBD_ProcessSetupPacket();
        }
        if(flags & USBD_INTSTS_EP0) { USBD_CLR_INT_FLAG(USBD_INTSTS_EP0); USBD_CtrlIn(); }
        if(flags & USBD_INTSTS_EP1) {
            USBD_CLR_INT_FLAG(USBD_INTSTS_EP1); USBD_CtrlOut();
            uint32_t toggle=USBD->EPSTS & USBD_EPSTS_EPSTS1_Msk;
            if(control_pending && toggle!=control_toggle) {
                control_toggle=toggle; control_count+=USBD_GET_PAYLOAD_LEN(EP1);
            }
            if(control_pending && control_count==64) {
                if(rh-rt<Q) { memcpy(rx[rh%Q],control_out,64); __DMB(); ++rh; }
                control_pending=false;
            }
        }
        if(flags & USBD_INTSTS_EP2) { USBD_CLR_INT_FLAG(USBD_INTSTS_EP2); in_busy=false; }
        if(flags & USBD_INTSTS_EP3) {
            USBD_CLR_INT_FLAG(USBD_INTSTS_EP3); out_armed=false;
            if(USBD_GET_PAYLOAD_LEN(EP3)==64 && rh-rt<Q) {
                copy_from_ep(EP3,rx[rh%Q],64); __DMB(); ++rh;
            }
            if(rh-rt<Q-(control_pending?1u:0u)) { USBD_SET_PAYLOAD_LEN(EP3,64); out_armed=true; }
        }
        if(flags & USBD_INTSTS_EP4) { USBD_CLR_INT_FLAG(USBD_INTSTS_EP4); bulk_busy=false; }
        if(flags & USBD_INTSTS_EP5) {
            USBD_CLR_INT_FLAG(USBD_INTSTS_EP5);
            bulk_length=USBD_GET_PAYLOAD_LEN(EP5); if(bulk_length>64) bulk_length=64;
            copy_from_ep(EP5,bulk_out,bulk_length); bulk_ready=true;
        }
    }
}
bool usb_send(const uint8_t p[64]) {
    uint32_t mask=__get_PRIMASK(); __disable_irq();
    if(!configured || reset_pending || th-tt==Q) { __set_PRIMASK(mask); return false; }
    memcpy(tx[th%Q],p,64);
    if(p[0]>=1 && p[0]<=4) memcpy(last_report[p[0]-1],p,64);
    __DMB(); ++th;
    __set_PRIMASK(mask); return true;
}
bool usb_idle(void) { return configured && th-tt<Q; }
void usb_disconnect(void) { USBD_DISABLE_USB(); NVIC_DisableIRQ(USBD_IRQn); }
void usb_request_mode(uint8_t m) { requested_mode=m; mode_pending=true; }
static void set_config(void) {
    uint8_t s[8]; USBD_GetSetupPacket(s); configured=s[2]!=0;
}
void usb_init(uint8_t m) {
    mode=m; rh=rt=th=tt=0; in_busy=control_pending=false;
    memset(last_report,0,sizeof(last_report));
    for(unsigned i=0;i<4;i++) last_report[i][0]=(uint8_t)(i+1);
    bulk_busy=bulk_ready=false; mode_pending=false; configured=false; msc_reset();
    info.gu8ConfigDesc=mode?composite_config:hid_config;
    USBD_Open(&info,class_request,0); USBD_SetConfigCallback(set_config);
    endpoints(); USBD_Start();
    /* StdDriver USBD_Start uses CLK_SysTickDelay, which disables SysTick.
     * Restore the 1-ms scheduler after every start, including mode changes;
     * otherwise WFI can leave a reply queued until the next USB request. */
    SysTick_Config(SystemCoreClock/1000);
    NVIC_EnableIRQ(USBD_IRQn);
}
void usb_poll(void) {
    if(reset_pending) { reset_pending=false; bridge_reset_transport(&bridge); msc_reset(); }
    if(msc_reset_pending) { msc_reset_pending=false; msc_reset(); }
    if(!configured) return;
    if(!in_busy && tt!=th) {
        uint32_t mask=__get_PRIMASK(); __disable_irq();
        if(!configured || tt==th) { __set_PRIMASK(mask); return; }
        copy_to_ep(EP2,tx[tt%Q],64); ++tt; in_busy=true;
        USBD_SET_PAYLOAD_LEN(EP2,64); __set_PRIMASK(mask);
    }
    if(rt!=rh && usb_idle()) {
        uint8_t r[64]; uint32_t mask=__get_PRIMASK(); __disable_irq();
        if(!configured || rt==rh) { __set_PRIMASK(mask); return; }
        memcpy(r,rx[rt%Q],64); ++rt;
        if(!out_armed && rh-rt<Q-(control_pending?1u:0u)) { USBD_SET_PAYLOAD_LEN(EP3,64); out_armed=true; }
        __set_PRIMASK(mask); bridge_report(&bridge,r,64);
    }
    if(reset_pending) return;
    if(mode && bulk_ready) {
        uint8_t data[64]; uint32_t mask=__get_PRIMASK(); __disable_irq();
        if(!configured || !bulk_ready) { __set_PRIMASK(mask); return; }
        size_t n=bulk_length; memcpy(data,bulk_out,n); bulk_ready=false;
        __set_PRIMASK(mask); msc_out(data,n);
        if(reset_pending || msc_reset_pending) return;
        USBD_SET_PAYLOAD_LEN(EP5,64);
    }
    if(mode && !bulk_busy && msc_in_pending()) {
        uint32_t mask=__get_PRIMASK(); __disable_irq();
        if(!configured || reset_pending || msc_reset_pending) { __set_PRIMASK(mask); return; }
        uint8_t data[64]; size_t n=msc_in(data);
        copy_to_ep(EP4,data,n); bulk_busy=true; USBD_SET_PAYLOAD_LEN(EP4,n);
        __set_PRIMASK(mask);
    }
    if(mode && msc_halted() && !bulk_busy) {
        USBD_LockEpStall(BIT4|BIT5); USBD_SET_EP_STALL(EP4); USBD_SET_EP_STALL(EP5);
    }
    if(mode_pending && th==tt && !in_busy) {
        uint8_t next=requested_mode; mode_pending=false;
        usb_disconnect(); board_delay(100); bridge_reset_transport(&bridge); usb_init(next);
    }
}
