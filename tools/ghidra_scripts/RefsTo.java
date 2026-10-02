//List all references to the given addresses, with the function containing each reference.
//Catches indirect and data references that a call-opcode scan misses.
//Usage: -postScript RefsTo.java /abs/out.txt 0xc2bcc,0xc2c38,...
//@category NT68503
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import java.io.*;

public class RefsTo extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 2) { println("RefsTo: need out path and addresses"); return; }
        try (PrintWriter w = new PrintWriter(new FileWriter(args[0]))) {
            for (String a : args[1].split(",")) {
                a = a.trim();
                if (a.isEmpty()) continue;
                Address addr = currentProgram.getAddressFactory().getDefaultAddressSpace()
                        .getAddress(Long.parseLong(a.replace("0x", ""), 16));
                Function tgt = getFunctionContaining(addr);
                w.println("==== " + a + (tgt != null ? "  " + tgt.getName() : "  <no function>"));
                ReferenceIterator it = currentProgram.getReferenceManager().getReferencesTo(addr);
                int n = 0;
                while (it.hasNext()) {
                    Reference r = it.next();
                    Address from = r.getFromAddress();
                    Function f = getFunctionContaining(from);
                    w.println("    " + r.getReferenceType() + "  from " + from
                            + (f != null ? "  in " + f.getName() + " @ " + f.getEntryPoint()
                                         : "  in <no function>"));
                    n++;
                }
                w.println("    total: " + n);
            }
        }
        println("REFSTO   : written -> " + args[0]);
    }
}
