//Add the SRAM and peripheral windows a Cortex-M raw image needs, and unpack the
//block the startup code relocates from flash into SRAM.
//Without the windows every reference to 0x2000xxxx or 0x400xxxxx lands outside
//the program and the decompiler shows a bare constant. Without the relocated
//block a third of the interrupt handlers point at empty SRAM: this firmware
//runs its I2C, timer and GPIO handlers from RAM.
//Usage: -preScript AddCortexMem.java [src_hex dst_hex len_hex]
//@category NT68503
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.mem.MemoryBlock;

public class AddCortexMem extends GhidraScript {
    // start, size -- NUC1261: 20 KB SRAM, APB/AHB peripherals in two windows,
    // plus the Cortex-M0 System Control Space.
    private static final long[][] BLOCKS = {
        {0x20000000L, 0x5000L},      // SRAM
        {0x40000000L, 0x100000L},    // AHB/APB peripherals
        {0x50000000L, 0x100000L},    // SYS, CLK, FMC, INT
        {0xE000E000L, 0x1000L},      // SCS: NVIC, SysTick, SCB
    };
    private static final String[] NAMES = {"SRAM", "PERIPH_4", "PERIPH_5", "SCS"};

    public void run() throws Exception {
        String[] args = getScriptArgs();
        for (int i = 0; i < BLOCKS.length; i++) {
            Address a = toAddr(BLOCKS[i][0]);
            if (currentProgram.getMemory().getBlock(a) != null) continue;
            MemoryBlock b;
            if (i == 0) {
                // SRAM has to be initialised so the relocated block can be
                // written into it below.
                b = currentProgram.getMemory().createInitializedBlock(
                        NAMES[i], a, BLOCKS[i][1], (byte) 0, monitor, false);
            } else {
                b = currentProgram.getMemory().createUninitializedBlock(
                        NAMES[i], a, BLOCKS[i][1], false);
                b.setVolatile(true);
            }
            b.setRead(true);
            b.setWrite(true);
            b.setExecute(i == 0);
            println("BLOCK    : " + NAMES[i] + " @ " + a + " size "
                    + Long.toHexString(BLOCKS[i][1]));
        }
        if (args.length >= 3) {
            long src = Long.decode(args[0]), dst = Long.decode(args[1]),
                 len = Long.decode(args[2]);
            byte[] buf = new byte[(int) len];
            currentProgram.getMemory().getBytes(toAddr(src), buf);
            currentProgram.getMemory().setBytes(toAddr(dst), buf);
            println("RELOC    : " + Long.toHexString(len) + " bytes "
                    + Long.toHexString(src) + " -> " + Long.toHexString(dst));
        }
    }
}
