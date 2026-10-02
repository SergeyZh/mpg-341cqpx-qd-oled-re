/* SPDX-License-Identifier: MIT */
#include "NUC1261.h"
#include "board.h"
#include "boot_metadata.h"
#include <string.h>

static volatile uint32_t milliseconds;
static volatile uint8_t uart_data[2][512];
static volatile uint16_t uart_length[2];
static volatile uint32_t uart_last[2];
static volatile bool uart_overflow[2];
static uint32_t page_scratch[512];
static uint32_t default_trim,last_trim;
static uint32_t last_tick;
static bool service_i2c;

void SysTick_Handler(void) { ++milliseconds; }
uint32_t board_millis(void) { return milliseconds; }
void board_delay(uint32_t ms) {
    uint32_t start=board_millis();
    while((uint32_t)(board_millis()-start)<ms) __WFI();
}
static bool elapsed(uint32_t start,uint32_t ms) { return (uint32_t)(board_millis()-start)>=ms; }

static void receive(UART_T *uart,unsigned port) {
    while(!(uart->FIFOSTS & UART_FIFOSTS_RXEMPTY_Msk)) {
        uint8_t ch=(uint8_t)uart->DAT;
        if(uart_length[port]<512) uart_data[port][uart_length[port]++]=ch;
        else uart_overflow[port]=true;
        uart_last[port]=board_millis();
    }
    if(uart->FIFOSTS & (UART_FIFOSTS_RXOVIF_Msk|UART_FIFOSTS_FEF_Msk|UART_FIFOSTS_PEF_Msk)) {
        uart_overflow[port]=true;
        uart->FIFOSTS=UART_FIFOSTS_RXOVIF_Msk|UART_FIFOSTS_FEF_Msk|UART_FIFOSTS_PEF_Msk;
    }
}
void UART02_IRQHandler(void) { receive(UART0,0); }
void UART1_IRQHandler(void) { receive(UART1,1); }
static void uart_clear(unsigned port) {
    if(port>1) return;
    uint32_t mask=__get_PRIMASK(); __disable_irq();
    uart_length[port]=0; uart_overflow[port]=false;
    (port?UART1:UART0)->FIFO |= UART_FIFO_RXRST_Msk;
    __set_PRIMASK(mask);
}
static bool uart_write(unsigned port,const uint8_t *p,size_t n) {
    if(port>1 || (port==1 && service_i2c)) return false;
    UART_T *u=port?UART1:UART0;
    uint32_t start=board_millis();
    while(n--) {
        while(u->FIFOSTS & UART_FIFOSTS_TXFULL_Msk) if(elapsed(start,1000)) return false;
        u->DAT=*p++;
    }
    while(!(u->FIFOSTS & UART_FIFOSTS_TXEMPTY_Msk)) if(elapsed(start,1000)) return false;
    return true;
}
static bool set_mode(bool i2c) {
    UART1->INTEN=0; NVIC_DisableIRQ(UART1_IRQn);
    I2C0->CTL=0; NVIC_DisableIRQ(I2C0_IRQn);
    SYS->GPE_MFPH=(SYS->GPE_MFPH & ~0x00ff0000u) | (i2c?0x00440000u:0x00330000u);
    service_i2c=i2c;
    if(i2c) {
        I2C_Open(I2C0,100000); I2C0->CTL=I2C_CTL_I2CEN_Msk;
    } else {
        UART_Open(UART1,115200);
        UART1->FIFO=(UART1->FIFO & ~UART_FIFO_RFITL_Msk)|UART_FIFO_RFITL_4BYTES;
        UART1->TOUT=40;
        uart_clear(1);
        UART1->INTEN=UART_INTEN_RDAIEN_Msk|UART_INTEN_RXTOIEN_Msk|UART_INTEN_TOCNTEN_Msk;
        NVIC_EnableIRQ(UART1_IRQn);
    }
    return true;
}
static I2C_T *bus(unsigned n) { return n?I2C1:I2C0; }
static bool wait_si(I2C_T *i,uint32_t start) {
    /* One deadline covers the whole transaction. A 4098-byte ISP write at
     * 100 kHz needs at least 369 ms, before software overhead/clock stretching.
     */
    while(!(i->CTL & I2C_CTL_SI_Msk)) if(elapsed(start,1000)) return false;
    return true;
}
static void ctl(I2C_T *i,uint32_t flags) { i->CTL=I2C_CTL_I2CEN_Msk|flags; }
static void stop(I2C_T *i) {
    ctl(i,I2C_CTL_STO_Msk|I2C_CTL_SI_Msk);
    uint32_t start=board_millis();
    while(i->CTL&I2C_CTL_STO_Msk) {
        if(elapsed(start,5)) { i->CTL=0; i->CTL=I2C_CTL_I2CEN_Msk; break; }
    }
}
static bool start_address(I2C_T *i,uint8_t address,uint32_t start) {
    ctl(i,I2C_CTL_STA_Msk|I2C_CTL_SI_Msk);
    if(!wait_si(i,start) || (i->STATUS!=8 && i->STATUS!=0x10)) return false;
    i->DAT=address; ctl(i,I2C_CTL_SI_Msk);
    return wait_si(i,start);
}
static bool i2c_write(unsigned n,const uint8_t *p,size_t length,bool nack_start) {
    if(n>1 || !length || (n==0 && !service_i2c)) return false;
    I2C_T *i=bus(n); uint32_t start=board_millis();
    if(!start_address(i,*p++,start)) goto error;
    --length;
    for(;;) {
        uint32_t status=i->STATUS;
        if(status==0x20 && nack_start) {
            /* MSI A0/A1: each NACKed byte is followed by another START. */
            if(!length) break;
            if(!start_address(i,*p++,start)) goto error;
            --length; continue;
        }
        if(status!=0x18 && status!=0x28) goto error;
        if(!length) break;
        i->DAT=*p++; --length; ctl(i,I2C_CTL_SI_Msk);
        if(!wait_si(i,start)) goto error;
    }
    stop(i); return true;
error: stop(i); return false;
}
static bool read_data(I2C_T *i,uint8_t *p,size_t n,uint32_t start) {
    if(i->STATUS!=0x40) return false;
    for(size_t j=0;j<n;j++) {
        ctl(i,I2C_CTL_SI_Msk | (j+1<n?I2C_CTL_AA_Msk:0));
        if(!wait_si(i,start) || i->STATUS!=(j+1<n?0x50u:0x58u)) return false;
        p[j]=(uint8_t)i->DAT;
    }
    return true;
}
static bool i2c_read(unsigned n,uint8_t address,uint8_t *p,size_t length) {
    if(n>1 || !length || !(address&1) || (n==0 && !service_i2c)) return false;
    I2C_T *i=bus(n); uint32_t start=board_millis();
    bool ok=start_address(i,address,start) && read_data(i,p,length,start);
    stop(i); return ok;
}
static bool register_read(unsigned n,uint8_t address,uint8_t reg,uint8_t *p,size_t length) {
    if(n>1 || !length || address>0x7f || (n==0 && !service_i2c)) return false;
    I2C_T *i=bus(n); uint32_t start=board_millis();
    if(!start_address(i,(uint8_t)(address<<1),start) || i->STATUS!=0x18) goto error;
    i->DAT=reg; ctl(i,I2C_CTL_SI_Msk);
    if(!wait_si(i,start) || i->STATUS!=0x28) goto error;
    if(!start_address(i,(uint8_t)((address<<1)|1),start) || !read_data(i,p,length,start)) goto error;
    stop(i); return true;
error: stop(i); return false;
}
/* This function and its complete call path execute from SRAM while FMC is busy. */
__attribute__((section(".ramfunc"),noinline))
static bool fmc_command(uint32_t command,uint32_t address,uint32_t *data) {
    FMC->ISPCMD=command; FMC->ISPADDR=address;
    if(command==0x21) FMC->ISPDAT=*data;
    FMC->ISPTRG=1;
    for(uint32_t count=0;FMC->ISPTRG & 1;count++) {
        if(count==4800000) {
            /* Never return to flash while FMC may still be busy. */
            for(;;) __asm volatile("nop");
        }
    }
    if(FMC->ISPCTL & FMC_ISPCTL_ISPFF_Msk) { FMC->ISPCTL|=FMC_ISPCTL_ISPFF_Msk; return false; }
    if(command==0) *data=FMC->ISPDAT;
    return true;
}
static bool flash_read_word(uint32_t address,uint32_t *value) {
    uint32_t mask=__get_PRIMASK(); __disable_irq();
    SYS_UnlockReg(); uint32_t old=FMC->ISPCTL;
    FMC->ISPCTL=(old & ~(FMC_ISPCTL_APUEN_Msk|FMC_ISPCTL_LDUEN_Msk|FMC_ISPCTL_CFGUEN_Msk|FMC_ISPCTL_SPUEN_Msk))|1;
    bool ok=fmc_command(0,address,value);
    FMC->ISPCTL=old; SYS_LockReg(); __set_PRIMASK(mask);
    return ok;
}
static uint32_t flash_read(uint32_t address) {
    if(address==0x50000000) return SYS->PDID;
    uint32_t value=UINT32_MAX;
    if(!flash_read_word(address,&value)) return UINT32_MAX;
    return value;
}
static bool update_page(uint32_t base,unsigned offset,const uint8_t *data,size_t n) {
    if((base!=0x1f800 && base!=0x1e800 && !(base==0x1f000 && offset==2040 && n==8) &&
        !(base>=0x10000 && base<0x15800 && !(base&2047))) ||
        n>2048 || offset>2048-n) return false;
    if(FMC->DFBA!=0x1f800) return false;
    for(unsigned j=0;j<512;j++) if(!flash_read_word(base+4*j,page_scratch+j)) return false;
    if(!memcmp((uint8_t *)page_scratch+offset,data,n)) return true;
    memcpy((uint8_t *)page_scratch+offset,data,n);
    uint32_t mask=__get_PRIMASK(); __disable_irq();
    SYS_UnlockReg(); uint32_t old=FMC->ISPCTL;
    FMC->ISPCTL=(old & ~(FMC_ISPCTL_LDUEN_Msk|FMC_ISPCTL_CFGUEN_Msk|FMC_ISPCTL_SPUEN_Msk))|FMC_ISPCTL_APUEN_Msk|1;
    bool ok=fmc_command(0x22,base,page_scratch);
    for(unsigned j=0;ok && j<512;j++) ok=fmc_command(0x21,base+4*j,page_scratch+j);
    for(unsigned j=0;ok && j<512;j++) {
        uint32_t value=0; ok=fmc_command(0,base+4*j,&value) && value==page_scratch[j];
    }
    FMC->ISPCTL=old; SYS_LockReg(); __set_PRIMASK(mask);
    return ok;
}
static bool write_boot_metadata(const uint32_t words[2]) {
    /* update_page preserves the page and writes length/checksum as its last words. */
    return update_page(0x1f000,2040,(const uint8_t *)words,8);
}
bool board_prepare_image(void) {
    extern uint8_t _code_end;
    return FMC->DFBA==0x1f800 &&
        boot_metadata_prepare((uint32_t)&_code_end,flash_read_word,write_boot_metadata);
}
static bool settings_write(unsigned offset,const uint8_t *p,size_t n) {
    if(!((offset==0 && n==4)||(offset==4 && n==13))) return false;
    return update_page(0x1f800,offset,p,n);
}
void disk_read(uint32_t sector,uint8_t *p) {
    if(sector<DISK_SECTORS) memcpy(p,(const void *)(0x10000+sector*512),512);
    else memset(p,0,512);
}
bool disk_write(uint32_t sector,const uint8_t *p) {
    if(sector>=DISK_SECTORS) return false;
    uint32_t address=0x10000+sector*512;
    return update_page(address&~2047u,address&2047u,p,512);
}
void GPAB_IRQHandler(void) {
    if(PB->INTSRC & BIT3) { PB->INTSRC=BIT3; bridge_macro_event(&bridge); }
    PA->INTSRC=PA->INTSRC; PB->INTSRC=PB->INTSRC;
}
static bool usb_mode_write(uint8_t mode) {
    if(!update_page(0x1e800,0,&mode,1)) return false;
    usb_request_mode(mode); return true;
}
__attribute__((noreturn)) static void enter_ldrom(void) {
    usb_disconnect(); __disable_irq();
    SysTick->CTRL=0;
    NVIC->ICER[0]=UINT32_MAX; NVIC->ICPR[0]=UINT32_MAX;
    UART0->INTEN=UART1->INTEN=0;
    I2C0->CTL=I2C1->CTL=0;
    SYS_UnlockReg();
    FMC->ISPCTL=(FMC->ISPCTL & ~(FMC_ISPCTL_APUEN_Msk|FMC_ISPCTL_LDUEN_Msk|FMC_ISPCTL_CFGUEN_Msk|FMC_ISPCTL_SPUEN_Msk))|FMC_ISPCTL_BS_Msk|1;
    __DSB(); SYS->IPRST0=SYS_IPRST0_CPURST_Msk;
    for(;;) __NOP();
}
const struct bridge_io board_io={usb_send,uart_write,uart_clear,i2c_write,i2c_read,
    register_read,board_delay,set_mode,flash_read,settings_write,usb_mode_write,enter_ldrom};

void board_init(void) {
    SYS_UnlockReg();
    CLK_EnableXtalRC(CLK_PWRCTL_HIRCEN_Msk|CLK_PWRCTL_HIRC48EN_Msk);
    CLK_WaitClockReady(CLK_STATUS_HIRCSTB_Msk|CLK_STATUS_HIRC48STB_Msk);
    CLK_SetHCLK(CLK_CLKSEL0_HCLKSEL_HIRC48,CLK_CLKDIV0_HCLK(1));
    CLK_SetModuleClock(USBD_MODULE,CLK_CLKSEL3_USBDSEL_HIRC48,CLK_CLKDIV0_USB(1));
    CLK_SetModuleClock(UART0_MODULE,CLK_CLKSEL1_UARTSEL_HIRC,CLK_CLKDIV0_UART(1));
    CLK_SetModuleClock(UART1_MODULE,CLK_CLKSEL1_UARTSEL_HIRC,CLK_CLKDIV0_UART(1));
    CLK_EnableModuleClock(USBD_MODULE); CLK_EnableModuleClock(UART0_MODULE);
    CLK_EnableModuleClock(UART1_MODULE); CLK_EnableModuleClock(I2C0_MODULE); CLK_EnableModuleClock(I2C1_MODULE);
    SystemCoreClockUpdate(); SysTick_Config(SystemCoreClock/1000);
    default_trim=last_trim=*(volatile uint32_t *)0x50000118;
    SYS->GPD_MFPL=(SYS->GPD_MFPL & ~0xffu)|0x33;
    SYS->GPF_MFPL=(SYS->GPF_MFPL & ~0x000ff000u)|0x00033000;
    SYS->GPB_MFPL &= ~0x0000f000u;
    PB->MODE &= ~(3u<<6); GPIO->DBCTL=0x38;
    PB->DBEN |= BIT3; PB->INTTYPE &= ~BIT3; PB->INTEN |= BIT3;
    PB->INTSRC=BIT3; NVIC_EnableIRQ(GPAB_IRQn);
    UART_Open(UART0,115200); UART0->TOUT=40;
    UART0->INTEN=UART_INTEN_RDAIEN_Msk|UART_INTEN_RXTOIEN_Msk|UART_INTEN_TOCNTEN_Msk;
    NVIC_EnableIRQ(UART02_IRQn);
    set_mode(false);
    I2C_Open(I2C1,100000); I2C1->CTL=I2C_CTL_I2CEN_Msk;
    SYS_LockReg();
}
void board_poll(void) {
    uint32_t now=board_millis(); bridge_tick(&bridge,now-last_tick); last_tick=now;
    if((SYS->IRCTCTL1 & SYS_IRCTCTL1_FREQSEL_Msk)!=2 && (USBD->INTSTS & USBD_INTSTS_SOFIF_Msk)) {
        SYS_UnlockReg(); USBD->INTSTS=USBD_INTSTS_SOFIF_Msk; SYS->IRCTCTL1=0x512; SYS_LockReg();
    }
    if(SYS->IRCTISTS & (SYS_IRCTISTS_CLKERRIF1_Msk|SYS_IRCTISTS_TFAILIF1_Msk)) {
        SYS_UnlockReg(); *(volatile uint32_t *)0x50000118=last_trim; SYS->IRCTCTL1=0;
        SYS->IRCTISTS=SYS_IRCTISTS_CLKERRIF1_Msk|SYS_IRCTISTS_TFAILIF1_Msk;
        USBD->INTSTS=USBD_INTSTS_SOFIF_Msk; SYS_LockReg();
    }
    uint32_t trim=*(volatile uint32_t *)0x50000118;
    if(trim>default_trim+16 || trim+16<default_trim) {
        SYS_UnlockReg(); *(volatile uint32_t *)0x50000118=last_trim; SYS_LockReg();
    } else last_trim=trim;
    for(unsigned p=0;p<2;p++) {
        if(uart_length[p] && elapsed(uart_last[p],4) && usb_idle()) {
            uint8_t data[512]; uint16_t n;
            uint32_t mask=__get_PRIMASK(); __disable_irq();
            n=uart_length[p]; bool bad=uart_overflow[p];
            for(unsigned j=0;j<n;j++) data[j]=uart_data[p][j];
            uart_length[p]=0; uart_overflow[p]=false; __set_PRIMASK(mask);
            if(!bad) bridge_uart_received(&bridge,p,data,n);
        }
    }
}
