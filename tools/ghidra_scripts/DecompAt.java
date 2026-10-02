//Decompile only the functions at the given addresses.
//Usage: -postScript DecompAt.java /abs/out.c 0xc283c,0xc2a04,...
//@category NT68503
import ghidra.app.decompiler.*;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import java.io.*;

public class DecompAt extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 2) { println("DecompAt: need out path and addresses"); return; }
        DecompInterface di = new DecompInterface();
        di.openProgram(currentProgram);
        int n = 0, miss = 0;
        try (PrintWriter w = new PrintWriter(new FileWriter(args[0]))) {
            for (String a : args[1].split(",")) {
                a = a.trim();
                if (a.isEmpty()) continue;
                Address addr = currentProgram.getAddressFactory().getDefaultAddressSpace()
                        .getAddress(Long.parseLong(a.replace("0x", ""), 16));
                Function f = getFunctionAt(addr);
                if (f == null) f = createFunction(addr, null);
                if (f == null) { miss++; w.println("/* no function at " + a + " */"); continue; }
                DecompileResults r = di.decompileFunction(f, 90, monitor);
                w.println("/* ==== " + f.getName() + " @ " + f.getEntryPoint() + " ==== */");
                w.println(r != null && r.decompileCompleted()
                        ? r.getDecompiledFunction().getC() : "/* decompilation failed */");
                n++;
            }
        }
        di.dispose();
        println("DUMPED   : " + n + " functions, " + miss + " missing -> " + args[0]);
    }
}
