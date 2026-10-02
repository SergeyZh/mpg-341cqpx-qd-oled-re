/* SPDX-License-Identifier: MIT
 * MSI application v0x54 wire ABI, reconstructed from the APROM and USB captures.
 * All proprietary code stays outside this implementation.
 */
#include "bridge.h"
#include <string.h>

const uint8_t msi_uart_lengths[36] = {
 17,18,5,10,12,60,60,43,5,7,6,5,4,5,12,4,5,4,13,13,13,7,60,60,45,60,60,21,3,8,10,60,60,18,10,2};
const uint8_t msi_i2c_lengths[36] = {
 4,4,5,10,12,60,60,43,5,7,6,5,4,5,12,4,5,4,13,13,13,7,60,60,45,60,60,21,3,8,10,60,60,18,10,2};
const uint8_t msi_read_lengths[36] = {
 4,0,4,3,3,0,0,3,5,3,4,5,4,0,3,3,0,0,3,0,0,5,0,0,3,0,0,0,0,0,0,0,0,0,0,1};

static uint16_t le16(const uint8_t *p) { return (uint16_t)(p[0] | (uint16_t)p[1] << 8); }
static uint32_t le32(const uint8_t *p) {
    return p[0] | (uint32_t)p[1]<<8 | (uint32_t)p[2]<<16 | (uint32_t)p[3]<<24;
}
static void put16(uint8_t *p, uint16_t n) { p[0]=(uint8_t)n; p[1]=(uint8_t)(n>>8); }
static void put32be(uint8_t *p, uint32_t n) {
    p[0]=(uint8_t)(n>>24); p[1]=(uint8_t)(n>>16); p[2]=(uint8_t)(n>>8); p[3]=(uint8_t)n;
}
static uint8_t xor_bytes(uint8_t v, const uint8_t *p, size_t n) {
    while (n--) v ^= *p++;
    return v;
}
void bridge_reset_transport(struct bridge *b) {
    b->uart.active=b->i2c.active=false;
    b->uart.length=b->i2c.length=0;
    b->page_valid=false;
}
void bridge_init(struct bridge *b, const struct bridge_io *io) {
    memset(b,0,sizeof(*b)); b->io=io; b->hardware_revision=1;
    b->aux_timeout=5000;
    b->usb_mode=(uint8_t)io->flash_read(0x1e800);
    if (b->usb_mode==0xff) b->usb_mode=1;
    for (unsigned i=0;i<13;i++)
        b->settings[i]=(uint8_t)(io->flash_read(0x1f804+(i&~3u)) >> ((i&3u)*8));
}
static void local(struct bridge *b, const uint8_t *r) {
    uint8_t out[64]; memcpy(out,r,64);
    uint8_t *p=out+1;
    if (p[0]=='5' || p[0]=='8') {
        size_t length=63;
        while (length && p[length-1]!='\r') --length;
        if(!memcmp(p,"5b00Z",5) && p[5]==0xa6) length=p[41]=='\r'?42:0;
        if(!memcmp(p,"5b00Z",5) && p[5]==0xa7) length=p[10]=='\r'?11:0;
        if(!memcmp(p,"5b001",5) && p[5]>='i' && p[5]<='m') length=p[25]=='\r'?26:0;
        if (!length) return;
        if (length>=21 && !memcmp(p,"5b00130",7)) {
            if (!b->io->settings_write(4,p+7,13)) return;
            memcpy(b->settings,p+7,13); memcpy(p,"5600+\r",6);
        } else if (length>=8 && !memcmp(p,"5800130",7) &&
                   b->io->flash_read(0x1f804)!=UINT32_MAX) {
            memcpy(p,"5b00130",7); memcpy(p+7,b->settings,13); p[20]='\r';
        } else if (length==8 && !memcmp(p,"5800110\r",8)) {
            memcpy(p,b->macro_event?"5b00110001\r":"5b00110000\r",11);
            b->macro_event=0;
        } else {
            b->io->uart_clear(1);
            b->io->uart_write(1,p,length);
            return;
        }
    } else switch(p[0]) {
    case '6':
        if (memcmp(p,"6800;30\r",8)) return;
        memcpy(p,"6b00;30000\r",11); p[9]=(uint8_t)('0'+b->aux_event); b->aux_event=0;
        b->aux_connected=1; b->aux_timeout=5000;
        break;
    case 0xa0: b->io->enter_ldrom(); return;
    case 0xb0:
        p[0]=0x5a; p[1]=0x54;
        p[3]=(uint8_t)b->io->flash_read(0x100ff4);
        put32be(p+4,b->io->flash_read(0x100ffc));
        put32be(p+8,b->io->flash_read(0x1f7fc));
        p[12]=1; p[13]=b->hardware_revision;
        break;
    case 0xb2: p[0]=0x5a; put32be(p+1,b->io->flash_read(0x50000000)); break;
    case 0xb4: {
        uint32_t id=b->io->flash_read(0x1f800); p[0]=0x5a;
        for(unsigned i=0;i<4;i++) p[1+i]=(uint8_t)(id>>(8*i));
        break;
    }
    case 0xb6:
        if (!b->io->settings_write(0,p+1,4)) return;
        p[0]=0x5a; break;
    case 0xc0:
        memcpy(p,b->macro_event?"5b00110001\r":"5b00110000\r",11); b->macro_event=0; break;
    case 0xd0: {
        uint8_t mode=(uint8_t)(p[9]-'0');
        if (mode!=b->usb_mode && !b->io->usb_mode_write(mode)) return;
        b->usb_mode=mode; memcpy(p,"\xd0" "600+\r",6); break;
    }
    case 0xd2: memcpy(p,"\xd0" "b00000000\r",11); p[9]=(uint8_t)('0'+b->usb_mode); break;
    case 0xe0:
        if (p[1]>1) return;
        if (!b->io->set_mode(p[1]!=0)) return;
        b->i2c_mode=p[1]!=0; bridge_reset_transport(b); p[0]=0x5a; break;
    case 0xe2: /* Discovery is ignored by stock MSI; never probe stock Report 4 out of range. */
        memset(p,0,63); p[0]=0x5a; memcpy(p+1,"U7EX",4);
        p[5]=EXT_VERSION; p[6]=0x4a; p[7]=1; put16(p+8,512); p[10]=EXT_DATA_SIZE; break;
    default: return;
    }
    b->io->send(out);
}
/* All three stream families exist in MSI. B9/BA/BB are individual writes. */
static int append(struct stream *s, uint8_t sub, const uint8_t *p, size_t n) {
    unsigned part=0, family=0;
    if(sub>=0xa5 && sub<=0xa7) { family=1; part=sub-0xa5; }
    if(sub>=0xb6 && sub<=0xb8) { family=2; part=sub-0xb6; }
    if(sub>=0xbf && sub<=0xc1) { family=3; part=sub-0xbf; }
    if(!family || part==0) { s->length=0; s->active=family!=0; s->family=(uint8_t)family; }
    else if(!s->active || s->family!=family) return -1;
    if(n>STREAM_CAPACITY-s->length) { s->active=false; s->length=0; return -1; }
    memcpy(s->data+s->length,p,n); s->length+=(uint16_t)n;
    if(family && part!=2) return 0;
    s->active=false; return 1;
}
static void legacy_i2c(struct bridge *b,const uint8_t *r) {
    uint8_t out[64]={4,r[1],0,0};
    if(r[1]<0xa0 || r[1]>0xc3) return;
    unsigned index=r[1]-0xa0;
    int complete=append(&b->i2c,r[1],r+4,msi_i2c_lengths[index]);
    if(!complete) return;
    if(complete<0 || !b->i2c_mode) { b->io->send(out); return; }
    bool ok=b->io->i2c_write(0,b->i2c.data,b->i2c.length,r[1]==0xa0 || r[1]==0xa1);
    size_t n=msi_read_lengths[index];
    if(ok && r[2] && n) {
        b->io->delay_ms(r[1]==0xa7 || r[1]==0xab || r[1]==0xb5 || r[1]==0xb8 ? 10:2);
        out[4]=r[2]; ok=b->io->i2c_read(0,r[2],out+5,n);
    }
    if(ok) out[2]=1; else memset(out+4,0,60);
    b->io->send(out);
}
static void register_i2c(struct bridge *b,const uint8_t *r) {
    uint8_t out[64]={0}, wire[62];
    memcpy(out,r,4);
    uint8_t sub=r[1]; size_t n;
    if(r[2]>0x7f) return;
    wire[0]=(uint8_t)(r[2]<<1); wire[1]=r[3];
    bool ok=false;
    switch(sub) {
    case 0xa0: wire[2]=r[5]; ok=b->io->i2c_write(1,wire,3,false); out[4]=ok; break;
    case 0xa1:
        n=r[4]; if(!n || n>58) return;
        memcpy(wire+2,r+6,n); ok=b->io->i2c_write(1,wire,n+2,false);
        out[4]=r[4]; out[5]=ok; break;
    case 0xb0:
        ok=b->io->i2c_register_read(1,r[2],r[3],out+5,1); out[4]=ok; break;
    case 0xb1:
        n=r[4]; if(!n || n>58) return;
        ok=b->io->i2c_register_read(1,r[2],r[3],out+6,n);
        out[4]=r[4]; out[5]=ok; break;
    default: return;
    }
    b->io->send(out);
}
static void page_reply(struct bridge *b,uint8_t status,uint16_t token,uint16_t offset) {
    uint8_t out[64]={4,0x4a,EXT_VERSION,status};
    put16(out+4,token); put16(out+6,offset); put16(out+10,512);
    if(status==EXT_OK) {
        size_t n=512u-offset; if(n>EXT_DATA_SIZE) n=EXT_DATA_SIZE;
        out[8]=(uint8_t)n; out[9]=(offset+n<512);
        memcpy(out+12,b->page+2+offset,n);
    }
    b->io->send(out);
}
static void page_command(struct bridge *b,const uint8_t *r) {
    uint16_t token=le16(r+4), offset=le16(r+6);
    uint8_t status=EXT_OK;
    if(r[2]!=EXT_VERSION || r[3]<1 || r[3]>2 || offset>=512) status=EXT_BAD_REQUEST;
    else if(r[3]==2) {
        if(!b->page_valid) status=EXT_NO_PAGE;
        else if(token!=b->page_token) status=EXT_BAD_TOKEN;
    } else {
        b->page_valid=false;
        b->i2c.active=false; b->i2c.length=0;
        uint32_t address=le32(r+8);
        if(offset || (address&511) || address>0x01fffe00) status=EXT_BAD_REQUEST;
        else if(!b->i2c_mode) status=EXT_WRONG_MODE;
        else {
            uint8_t bank[5]={0x6e,2,0x0f,(uint8_t)(address>>24),0}, ack[4];
            bank[4]=xor_bytes(0x6e,bank+1,3);
            if(!b->io->i2c_write(0,bank,5,false)) status=EXT_IO_ERROR;
            else {
                b->io->delay_ms(20);
                if(!b->io->i2c_read(0,0x6f,ack,4)) status=EXT_IO_ERROR;
                else if(ack[0]!=2 || ack[1]!=0xf0 || ack[2]!=bank[3] ||
                        xor_bytes(0x6f,ack,4)) status=EXT_BAD_REPLY;
            }
            if(status==EXT_OK) {
                uint8_t cmd[7]={0x6e,4,0x4a,(uint8_t)(address>>16),(uint8_t)(address>>8),(uint8_t)address,0};
                cmd[6]=xor_bytes(0x6e,cmd+1,5);
                if(!b->io->i2c_write(0,cmd,7,false)) status=EXT_IO_ERROR;
                else {
                    b->io->delay_ms(20);
                    if(!b->io->i2c_read(0,0x6f,b->page,515)) status=EXT_IO_ERROR;
                    else if(b->page[1]!=0xb5 || xor_bytes(0x6f,b->page,515)) status=EXT_BAD_REPLY;
                }
            }
            if(status==EXT_OK) { b->page_token=token; b->page_address=address; b->page_valid=true; }
        }
    }
    page_reply(b,status,token,offset);
}
void bridge_report(struct bridge *b,const uint8_t *r,size_t n) {
    if(n!=64) return;
    switch(r[0]) {
    case 1: local(b,r); break;
    case 2:
        if(r[1]>=0xa0 && r[1]<=0xc3) {
            int complete=append(&b->uart,r[1],r+4,msi_uart_lengths[r[1]-0xa0]);
            if(complete==1) { b->uart_subcommand=r[1]; b->io->uart_write(1,b->uart.data,b->uart.length); }
        }
        break;
    case 3: register_i2c(b,r); break;
    case 4:
        if(r[1]==0x4a) page_command(b,r);
        else { b->page_valid=false; legacy_i2c(b,r); }
        break;
    default: break;
    }
}
void bridge_uart_received(struct bridge *b,unsigned port,const uint8_t *data,size_t n) {
    uint8_t out[64]={0};
    if(!n) return;
    if(port==0) {
        if(n<8 || data[n-1]!='\r' || memcmp(data,"5",1)) return;
        if(data[1]=='b') {
            bool ok=false;
            if(n>=11 && !memcmp(data+2,"0040",4)) {
                b->aux_value=(uint16_t)((data[7]-'0')*100+(data[8]-'0')*10+data[9]-'0'); ok=true;
            } else if(n>=11 && !memcmp(data+2,"00;3",4)) {
                b->aux_event=(uint8_t)(data[9]-'0'); ok=true;
            }
            b->io->uart_write(0,(const uint8_t *)(ok?"5600+\r":"5600-\r"),6);
        } else if(!memcmp(data,"580074",6) || !memcmp(data,"5800;4",6)) {
            memcpy(out,data,7); out[1]='b'; out[7]=out[8]='0';
            out[9]=(uint8_t)('0'+(data[4]==';'?b->aux_connected:0)); out[10]='\r';
            b->io->uart_write(0,out,11);
        }
        return;
    }
    if(port!=1) return;
    if(data[0]=='5' && data[n-1]=='\r') {
        out[0]=1; if(n>63) n=63; memcpy(out+1,data,n);
    } else if(n>=3 && data[0]==0x6f && data[1]==n-3) {
        out[0]=2; out[1]=b->uart_subcommand; if(n>60) n=60; memcpy(out+4,data,n);
    } else return;
    b->io->send(out);
}
void bridge_macro_event(struct bridge *b) { b->macro_event=1; }
void bridge_tick(struct bridge *b,uint32_t elapsed_ms) {
    if(b->aux_timeout>elapsed_ms) b->aux_timeout-=elapsed_ms;
    else { b->aux_timeout=5000-(elapsed_ms-b->aux_timeout)%5000; b->aux_connected=b->aux_event=0; }
}
