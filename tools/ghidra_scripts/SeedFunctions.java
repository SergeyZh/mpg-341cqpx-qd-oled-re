//Disassemble and create functions at explicit entry addresses, then re-run analysis.
//Use where the analyser never reached a callee (e.g. SPARC call targets found by a
//raw sweep). Addresses may be passed inline or as @/abs/file with one hex per line.
//Usage: -postScript SeedFunctions.java 0xef814,0xefadc   or   @/abs/seeds.txt
//@category NT68503
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import java.nio.file.*;
import java.util.*;

public class SeedFunctions extends GhidraScript {
    public void run() throws Exception {
        String arg = getScriptArgs()[0];
        List<String> items = arg.startsWith("@")
                ? Files.readAllLines(Paths.get(arg.substring(1)))
                : Arrays.asList(arg.split(","));
        int dis = 0, fun = 0, total = 0;
        for (String s : items) {
            s = s.trim();
            if (s.isEmpty()) continue;
            total++;
            Address a = toAddr(Long.parseLong(s.replace("0x", ""), 16));
            try {
                if (getInstructionAt(a) == null && disassemble(a)) dis++;
                if (getFunctionAt(a) == null && getInstructionAt(a) != null
                        && createFunction(a, null) != null) fun++;
            } catch (Exception e) { }
        }
        analyzeChanges(currentProgram);
        println("SEED     : " + total + " entries, " + dis + " disassembled, " + fun + " functions");
        println("FUNCS    : " + currentProgram.getFunctionManager().getFunctionCount());
    }
}
