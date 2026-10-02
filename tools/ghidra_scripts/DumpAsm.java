//Dump the disassembly listing for an address range.
//The 8051 decompiler output is unreliable where Keil banked calls confuse the
//function boundaries, so the raw listing is often the only readable form.
//Usage: -postScript DumpAsm.java out.txt 0x6e00 0x7200
//@category NT68503
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.CodeUnit;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.symbol.Reference;
import java.io.PrintWriter;

public class DumpAsm extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        Address start = toAddr(Long.parseLong(args[1].substring(2), 16));
        Address end = toAddr(Long.parseLong(args[2].substring(2), 16));
        PrintWriter out = new PrintWriter(args[0]);
        int n = 0;
        Address a = start;
        while (a.compareTo(end) < 0) {
            CodeUnit cu = currentProgram.getListing().getCodeUnitAt(a);
            if (cu == null) { a = a.add(1); continue; }
            StringBuilder sb = new StringBuilder();
            sb.append(String.format("%s  %-24s %s", a, cu.toString(),
                    getSymbolAt(a) != null ? "<" + getSymbolAt(a).getName() + ">" : ""));
            if (cu instanceof Instruction) {
                for (Reference r : cu.getReferencesFrom())
                    sb.append(" -> ").append(r.getToAddress());
                n++;
            }
            out.println(sb.toString().replaceAll("\\s+$", ""));
            a = a.add(cu.getLength());
        }
        out.close();
        println("DUMPED   : " + n + " instructions to " + args[0]);
    }
}
