//Dump decompiled C for every function to a file.
//Usage: -postScript DumpDecomp.java /abs/path/out.c
//@category NT68503
import ghidra.app.decompiler.*;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;
import java.io.*;

public class DumpDecomp extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 1) { println("DumpDecomp: need an output path"); return; }
        DecompInterface di = new DecompInterface();
        di.openProgram(currentProgram);
        int n = 0;
        try (PrintWriter w = new PrintWriter(new FileWriter(args[0]))) {
            for (Function f : currentProgram.getListing().getFunctions(true)) {
                if (monitor.isCancelled()) break;
                DecompileResults r = di.decompileFunction(f, 60, monitor);
                w.println("/* ==== " + f.getName() + " @ " + f.getEntryPoint()
                          + " ==== */");
                if (r != null && r.decompileCompleted())
                    w.println(r.getDecompiledFunction().getC());
                else
                    w.println("/* decompilation failed */");
                n++;
            }
        }
        di.dispose();
        println("DUMPED   : " + n + " functions to " + args[0]);
    }
}
