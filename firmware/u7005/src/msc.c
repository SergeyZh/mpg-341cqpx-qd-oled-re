/* SPDX-License-Identifier: MIT
 * Single-LUN SCSI / USB Bulk-Only Transport. No access outside the virtual disk.
 */
#include "board.h"
#include <string.h>
enum state { CBW, DATA_IN, DATA_OUT, ZLP, CSW, HALTED };
static enum state state;
static uint8_t sector[512],reply[96],tag[4],status,sense_key,sense_asc;
static const uint8_t inquiry[36]={0,0x80,0,0,31,0,0,0,'M','S','I',0,0,0,0,0,
    'O','p','t','i','x',' ','D','r','i','v','e','r',0,0,0,0,'1','.','0','0'};
static const uint8_t mode01[]={1,10,0,3,0,0,0,0,3,0,0,0};
static const uint8_t mode05[]={5,30,0x13,0x88,2,0x40,2,0,0,0,0,0,0,0,0,0,0,0,0,5,30,0,0,0,0,0,0,0,1,0x68,0,0};
static const uint8_t mode1b[]={0x1b,10,0,1,0,0,0,0,0,0,0,0};
static const uint8_t mode1c[]={0x1c,6,0,5,0,0,0,0};
static uint32_t host_length,remaining,residue,lba,position;
static bool reading,writing,host_in,phase_reset;
static uint32_t be32(const uint8_t *p) { return (uint32_t)p[0]<<24|(uint32_t)p[1]<<16|(uint32_t)p[2]<<8|p[3]; }
static uint32_t le32(const uint8_t *p) { return (uint32_t)p[3]<<24|(uint32_t)p[2]<<16|(uint32_t)p[1]<<8|p[0]; }
static void putbe(uint8_t *p,uint32_t v) { p[0]=(uint8_t)(v>>24); p[1]=(uint8_t)(v>>16); p[2]=(uint8_t)(v>>8); p[3]=(uint8_t)v; }
static void putle(uint8_t *p,uint32_t v) { p[3]=(uint8_t)(v>>24); p[2]=(uint8_t)(v>>16); p[1]=(uint8_t)(v>>8); p[0]=(uint8_t)v; }
void msc_reset(void) { state=CBW; sense_key=sense_asc=0; phase_reset=false; }
bool msc_halted(void) { return state==HALTED; }
bool msc_in_pending(void) { return state==DATA_IN || state==ZLP || state==CSW; }
static void failed(uint8_t key,uint8_t asc) {
    status=1; sense_key=key; sense_asc=asc; writing=reading=false;
}
static void command(const uint8_t *c,unsigned cdb_length) {
    uint32_t wanted=0; bool direction_in=true;
    unsigned minimum=(c[0]>>5)==0?6:((c[0]>>5)==5?12:10);
    if(c[0]==0x9e) minimum=16;
    reading=writing=false; position=0; memset(reply,0,sizeof(reply));
    if(cdb_length<minimum) { failed(5,0x24); goto transfer; }
    switch(c[0]) {
    case 0x00: case 0x1b: case 0x2f: case 0x35: break;
    case 0x1e: if(c[4]&1) failed(5,0x24); break;
    case 0x03:
        reply[0]=0x70; reply[2]=sense_key; reply[7]=10; reply[12]=sense_asc;
        wanted=c[4]<18?c[4]:18; sense_key=sense_asc=0; break;
    case 0x12:
        if((c[1]&1) || c[2]) { failed(5,0x24); break; }
        memcpy(reply,inquiry,36); wanted=c[4]<36?c[4]:36; break;
    case 0x1a: reply[0]=3; reply[2]=0x80; wanted=c[4]<4?c[4]:4; break;
    case 0x5a: {
        /* Retain MSI's mode-page layout, including its byte-0 length convention. */
        unsigned pos=8; uint8_t page=c[2]&63;
        if(page==1 || page==63) { memcpy(reply+pos,mode01,sizeof(mode01)); pos+=sizeof(mode01); }
        if(page==5 || page==63) { memcpy(reply+pos,mode05,sizeof(mode05)); pos+=sizeof(mode05); }
        if(page==0x1b || page==63) { memcpy(reply+pos,mode1b,sizeof(mode1b)); pos+=sizeof(mode1b); }
        if(page==0x1c || page==63) { memcpy(reply+pos,mode1c,sizeof(mode1c)); pos+=sizeof(mode1c); }
        if(pos==8) { failed(5,0x24); break; }
        reply[0]=(uint8_t)(pos-1);
        uint32_t alloc=(uint32_t)c[7]<<8|c[8]; wanted=alloc<pos?alloc:pos; break;
    }
    case 0x15: case 0x55: /* Consume mode parameters; no configurable disk caching. */
        direction_in=false; wanted=c[0]==0x15?c[4]:((uint32_t)c[7]<<8|c[8]); break;
    case 0x23:
        reply[3]=16; putbe(reply+4,DISK_SECTORS); reply[8]=2; reply[10]=2;
        putbe(reply+12,DISK_SECTORS); reply[18]=2;
        wanted=(uint32_t)c[7]<<8|c[8]; if(wanted>20) wanted=20; break;
    case 0x25: putbe(reply,DISK_SECTORS-1); putbe(reply+4,512); wanted=8; break;
    case 0x9e:
        if((c[1]&31)!=0x10) { failed(5,0x24); break; }
        putbe(reply+4,DISK_SECTORS-1); putbe(reply+8,512);
        wanted=be32(c+10); if(wanted>32) wanted=32; break;
    case 0x28: case 0x2a: case 0xa8: case 0xaa: {
        lba=be32(c+2);
        uint32_t count=(c[0]&0x80)?be32(c+6):((uint32_t)c[7]<<8|c[8]);
        if(lba>=DISK_SECTORS || count>DISK_SECTORS-lba) { failed(5,0x21); break; }
        wanted=count*512; reading=(c[0]==0x28 || c[0]==0xa8); writing=!reading;
        direction_in=reading; break;
    }
    default: failed(5,0x20); break;
    }
transfer:
    residue=host_length;
    if(!host_length) {
        if(wanted) { status=2; phase_reset=true; }
        state=CSW; return;
    }
    if(wanted && direction_in!=host_in) {
        /* Wrong direction: stop all bulk traffic until BOT reset recovery. */
        state=HALTED; return;
    }
    remaining=host_length;
    if(host_in) {
        if(wanted<remaining) remaining=wanted;
        if(host_length<wanted) { status=2; phase_reset=true; }
        state=remaining?DATA_IN:ZLP;
    } else {
        if(wanted!=host_length && !status) { status=2; phase_reset=true; writing=false; }
        state=DATA_OUT;
    }
}
void msc_out(const uint8_t *p,size_t n) {
    if(state==CBW) {
        if(n!=31 || memcmp(p,"USBC",4) || p[13]!=0 || (p[12]&0x7f) || p[14]<1 || p[14]>16) {
            state=HALTED; return;
        }
        memcpy(tag,p+4,4); host_length=le32(p+8); host_in=(p[12]&0x80)!=0;
        status=0; phase_reset=false; command(p+15,p[14]); return;
    }
    if(state!=DATA_OUT) { state=HALTED; return; }
    if(n>64 || n>remaining || !n) { state=HALTED; return; }
    if(writing && !status) {
        memcpy(sector+position,p,n); position+=(uint32_t)n;
        if(position==512) {
            if(!disk_write(lba++,sector)) failed(3,0x0c);
            else residue-=512;
            position=0;
        }
    } else if(!status) residue-=(uint32_t)n;
    remaining-=(uint32_t)n;
    if(!remaining) state=CSW;
    else if(n<64) { status=2; phase_reset=true; state=CSW; }
}
size_t msc_in(uint8_t *p) {
    if(state==ZLP) { state=CSW; return 0; }
    if(state==CSW) {
        memcpy(p,"USBS",4); memcpy(p+4,tag,4); putle(p+8,residue); p[12]=status;
        state=phase_reset?HALTED:CBW; return 13;
    }
    if(state!=DATA_IN) return 0;
    size_t n=remaining>64?64:remaining;
    if(reading) {
        if(!position) disk_read(lba,sector);
        memcpy(p,sector+position,n); position+=(uint32_t)n;
        if(position==512) { position=0; ++lba; }
    } else { memcpy(p,reply+position,n); position+=(uint32_t)n; }
    remaining-=(uint32_t)n; residue-=(uint32_t)n;
    if(!remaining) state=(residue && n==64)?ZLP:CSW;
    return n;
}
