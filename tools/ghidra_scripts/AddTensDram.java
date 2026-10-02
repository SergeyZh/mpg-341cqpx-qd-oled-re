//Create the Tensilica DRAM blocks from the section table at file 0x3AC38.
//Without them l32r resolves to nothing: strings, the literal pool and .data all
//live in DRAM at 0x3FFExxxx, not at the flash addresses they are copied from.
//Usage: -postScript AddTensDram.java /abs/FW.bin [table-file-offset]
//The default is FW.037; FW.034 requires 0x3AB38. Set image base first.
//@category NT68503
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import java.io.*;
import java.nio.file.*;

public class AddTensDram extends GhidraScript {
    // The image is linked at 0x40000000, which is file offset 0x30000.
    private static final long BASE = 0x40000000L;
    private static final int  FILE_OFF = 0x30000;
    private static final int  TABLE = 0x3AC38;

    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 1) { println("AddTensDram: need the firmware path"); return; }
        byte[] fw = Files.readAllBytes(Paths.get(args[0]));
        int table = args.length > 1 ? Integer.decode(args[1]) : TABLE;
        int n = 0;
        for (int e = table; ; e += 12) {
            long dst = le32(fw, e), end = le32(fw, e + 4), src = le32(fw, e + 8);
            if (dst == 0) break;
            int size = (int) (end - dst);
            if (size <= 0) continue;                    // empty section
            int off = (int) (src - BASE) + FILE_OFF;
            byte[] buf = new byte[size];
            System.arraycopy(fw, off, buf, 0, size);
            Address at = currentProgram.getAddressFactory().getDefaultAddressSpace()
                    .getAddress(dst);
            currentProgram.getMemory().createInitializedBlock(
                    "dram" + n, at, new ByteArrayInputStream(buf), size, monitor, false);
            n++;
        }
        println("DRAMBLOCKS: " + n);
    }

    private static long le32(byte[] b, int o) {
        return (b[o] & 0xffL) | (b[o + 1] & 0xffL) << 8
             | (b[o + 2] & 0xffL) << 16 | (b[o + 3] & 0xffL) << 24;
    }
}
