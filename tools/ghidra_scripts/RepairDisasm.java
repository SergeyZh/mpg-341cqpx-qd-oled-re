//Replace misclassified data with code in explicitly proven inclusive ranges.
//Usage: -postScript RepairDisasm.java 0xB263-0xB266
//@category NT68503
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
public class RepairDisasm extends GhidraScript {
    public void run() throws Exception {
        for (String range : getScriptArgs()[0].split(",")) {
            String[] ends = range.split("-");
            Address start = toAddr(Long.decode(ends[0]));
            Address end = toAddr(Long.decode(ends[1]));
            if (start.compareTo(end) > 0) throw new IllegalArgumentException(range);
            clearListing(start, end);
            if (!disassemble(start)) throw new IllegalStateException(range);
            println("REPAIRED: " + range);
        }
        analyzeChanges(currentProgram);
    }
}
