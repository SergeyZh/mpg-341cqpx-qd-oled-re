/* SPDX-License-Identifier: MIT: native test HAL, never touches a USB device. */
#include "board.h"
#include <string.h>
struct bridge bridge;
uint8_t sent[64],wire[8192],storage[44*512],flash[0x20000];
unsigned sends,wire_length,write_bus,write_restart,read_length,read_bus,read_address,uart_port;
unsigned writes,reads,delay_total,ldrom_entries,settings_writes;
bool io_ok=true, corrupt=false;
bool read_override=false;
bool corrupt_page=false;
uint8_t page_opcode=0xb5;
uint8_t read_fixture[8];
static bool send(const uint8_t *p) { memcpy(sent,p,64); ++sends; return true; }
static bool uart(unsigned port,const uint8_t *p,size_t n) { uart_port=port; memcpy(wire,p,n); wire_length=n; ++writes; return io_ok; }
static void clear(unsigned port) { (void)port; }
static bool write_i2c(unsigned bus,const uint8_t *p,size_t n,bool restart) {
    write_bus=bus; write_restart=restart; memcpy(wire,p,n); wire_length=n; ++writes; return io_ok;
}
static bool read_i2c(unsigned bus,uint8_t address,uint8_t *p,size_t n) {
    read_bus=bus; read_address=address; read_length=n; ++reads;
    for(size_t i=0;i<n;i++) p[i]=(uint8_t)(i+0x30);
    if(n==4 && wire_length==5 && wire[2]==0x0f) {
        p[0]=2; p[1]=0xf0; p[2]=wire[3]; p[3]=0x6f^p[0]^p[1]^p[2];
    }
    if(n==515) {
        p[0]=0; p[1]=page_opcode; uint8_t sum=0x6f^page_opcode;
        for(unsigned j=0;j<512;j++) { p[j+2]=(uint8_t)(j^(j>>8)); sum^=p[j+2]; }
        p[514]=sum^(corrupt_page?1:0);
    }
    if(corrupt) p[n-1]^=1;
    if(read_override && n<=8) memcpy(p,read_fixture,n);
    return io_ok;
}
static bool reg_read(unsigned bus,uint8_t address,uint8_t reg,uint8_t *p,size_t n) {
    wire[0]=reg; return read_i2c(bus,address,p,n);
}
static void delay(uint32_t ms) { delay_total+=ms; }
static bool mode(bool m) { (void)m; return io_ok; }
static uint32_t flash_read(uint32_t a) {
    if(a==0x100ff4) return 0x15;
    if(a==0x100ffc) return 0xd926;
    if(a==0x50000000) return 0x00126108;
    uint32_t v; if(a>sizeof(flash)-4) return UINT32_MAX;
    memcpy(&v,flash+a,4); return v;
}
static bool settings(unsigned a,const uint8_t *p,size_t n) {
    ++settings_writes; if(io_ok) memcpy(flash+0x1f800+a,p,n); return io_ok;
}
static bool usb_mode(uint8_t m) { if(io_ok) flash[0x1e800]=m; return io_ok; }
static void ldrom(void) { ++ldrom_entries; }
const struct bridge_io board_io={send,uart,clear,write_i2c,read_i2c,reg_read,delay,mode,
    flash_read,settings,usb_mode,ldrom};
void mock_init(void) {
    memset(flash,0xff,sizeof(flash)); flash[0x1e800]=1;
    flash[0x1f7fc]=0x0f; flash[0x1f7fd]=0x4f; flash[0x1f7fe]=flash[0x1f7ff]=0;
    memset(storage,0,sizeof(storage));
    sends=writes=reads=delay_total=ldrom_entries=settings_writes=0; io_ok=true; corrupt=read_override=false;
    corrupt_page=false; page_opcode=0xb5;
    bridge_init(&bridge,&board_io); msc_reset();
}
void mock_report(const uint8_t *p,size_t n) { bridge_report(&bridge,p,n); }
void mock_uart(unsigned port,const uint8_t *p,size_t n) { bridge_uart_received(&bridge,port,p,n); }
void mock_reset(void) { bridge_reset_transport(&bridge); }
void mock_macro(void) { bridge_macro_event(&bridge); }
void mock_tick(unsigned elapsed) { bridge_tick(&bridge,elapsed); }
void disk_read(uint32_t lba,uint8_t *p) { memcpy(p,storage+lba*512,512); }
bool disk_write(uint32_t lba,const uint8_t *p) { if(lba>=44 || !io_ok) return false; memcpy(storage+lba*512,p,512); return true; }
