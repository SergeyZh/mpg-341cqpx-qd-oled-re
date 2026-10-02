/* SPDX-License-Identifier: MIT */
#include "board.h"
extern void mock_init(void),mock_report(const uint8_t *,size_t),mock_uart(unsigned,const uint8_t *,size_t);
static uint32_t random_state=7005;
static uint32_t next(void) { random_state^=random_state<<13; random_state^=random_state>>17; return random_state^=random_state<<5; }
int main(void) {
    uint8_t p[512],out[64]; mock_init();
    for(unsigned i=0;i<50000;i++) {
        for(unsigned j=0;j<sizeof(p);j++) p[j]=(uint8_t)next();
        p[0]=(uint8_t)(next()%6); mock_report(p,next()%66);
        mock_uart(next()%3,p,next()%513);
        msc_reset(); msc_out(p,next()%65);
        for(unsigned j=0;j<4 && msc_in_pending();j++) msc_in(out);
        if(!(i%256)) mock_init();
    }
    return 0;
}
