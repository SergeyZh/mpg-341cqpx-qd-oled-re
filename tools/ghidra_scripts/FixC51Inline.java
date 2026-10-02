//Fix Keil C51 inline-constant helper: LCALL 0x09bd followed by 4 inline data bytes.
//@category NT68503
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.data.ByteDataType;

public class FixC51Inline extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        long helper = Long.parseLong(args[0].substring(2), 16);
        byte[] pat = new byte[]{0x12, (byte)((helper>>8)&0xff), (byte)(helper&0xff)};
        Memory mem = currentProgram.getMemory();
        Address min = currentProgram.getMinAddress(), max = currentProgram.getMaxAddress();
        int n=0, dis=0;
        Address a = min;
        while (true) {
            Address f = mem.findBytes(a, max, pat, null, true, monitor);
            if (f == null) break;
            a = f.add(1);
            Address data = f.add(3);
            Address resume = f.add(7);
            try {
                clearListing(data, data.add(3));
                createData(data, new ByteDataType());
                createData(data.add(1), new ByteDataType());
                createData(data.add(2), new ByteDataType());
                createData(data.add(3), new ByteDataType());
                n++;
                if (getInstructionAt(resume) == null) { if (disassemble(resume)) dis++; }
            } catch (Exception e) { println("skip " + f + ": " + e); }
        }
        println("PATCHED  : " + n + " sites, disassembled " + dis);
        println("INSTRS   : " + currentProgram.getListing().getNumInstructions());
    }
}
