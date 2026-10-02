//Seed disassembly at architecture entry points, then let analysis follow.
//A raw binary import has no entry point, so Ghidra disassembles nothing.
//Usage: -postScript AddEntries.java 8051      (reset + interrupt vectors)
//       -postScript AddEntries.java sparc     (trap table entries)
//@category NT68503
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSpace;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.SourceType;

public class AddEntries extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String kind = args.length > 0 ? args[0] : "8051";
        AddressSpace sp = currentProgram.getAddressFactory().getDefaultAddressSpace();
        Address base = currentProgram.getImageBase();
        long len = 0;
        for (MemoryBlock b : currentProgram.getMemory().getBlocks()) len += b.getSize();

        long[] offsets;
        if (kind.startsWith("0x")) {
            // Explicit comma-separated entry offsets, for images whose vector
            // area holds ordinary code (the STBC AUX image starts with a bare
            // LJMP and no interrupt table).
            String[] parts = kind.split(",");
            offsets = new long[parts.length];
            for (int i = 0; i < parts.length; i++)
                offsets[i] = Long.parseLong(parts[i].trim().substring(2), 16);
        } else if (kind.equals("8051")) {
            // Reset at 0, then the 8051 interrupt vectors every 8 bytes.
            offsets = new long[]{0x00, 0x03, 0x0B, 0x13, 0x1B, 0x23, 0x2B,
                                 0x33, 0x3B, 0x43, 0x4B, 0x53, 0x5B};
        } else {
            // SPARC trap table: 256 entries of 4 instructions (16 bytes).
            offsets = new long[64];
            for (int i = 0; i < offsets.length; i++) offsets[i] = i * 16L;
        }

        int seeded = 0;
        for (long off : offsets) {
            if (off >= len) break;
            Address a = base.add(off);
            try {
                disassemble(a);
                Function f = getFunctionAt(a);
                if (f == null) createFunction(a, null);
                addEntryPoint(a);
                seeded++;
            } catch (Exception e) {
                // Not every vector slot holds code; skip quietly.
            }
        }
        println("SEEDED   : " + seeded + " entry points (" + kind + ")");
        analyzeChanges(currentProgram);
        int funcs = 0;
        for (Function f : currentProgram.getListing().getFunctions(true)) funcs++;
        println("AFTERSEED: " + funcs + " functions, "
                + currentProgram.getListing().getNumInstructions() + " instructions");
    }
}
