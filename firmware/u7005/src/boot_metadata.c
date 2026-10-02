/* SPDX-License-Identifier: MIT */
#include "boot_metadata.h"

bool boot_metadata_prepare(uint32_t code_length,
    bool (*read_word)(uint32_t,uint32_t *),bool (*write_metadata)(const uint32_t [2])) {
    uint32_t length,stored,sum=0,code_sum=0;
    if(code_length<208 || code_length>0x10000 || (code_length&3)) return false;
    if(!read_word(U7005_USB_LENGTH,&length) ||
       !read_word(U7005_USB_LENGTH+4,&stored)) return false;
    if((length!=code_length && length!=U7005_USB_LENGTH) || stored>65535) return false;
    for(uint32_t address=0;address<length;address+=4) {
        uint32_t word;
        if(!read_word(address,&word)) return false;
        sum=(sum+(word&255)+((word>>8)&255)+((word>>16)&255)+(word>>24))&65535;
        if(address+4==code_length) code_sum=sum;
    }
    if(sum!=stored) return false;
    if(length==code_length) return true; /* No flash wear on normal boots. */
    const uint32_t metadata[2]={code_length,code_sum};
    if(!write_metadata(metadata)) return false;
    /* Do not expose mutable regions unless the new metadata read back correctly. */
    return read_word(U7005_USB_LENGTH,&length) && length==code_length &&
           read_word(U7005_USB_LENGTH+4,&stored) && stored==code_sum;
}
