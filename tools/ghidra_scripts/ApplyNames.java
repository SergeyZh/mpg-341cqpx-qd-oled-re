//Apply function names from a CSV produced by tools/name_by_strings.py.
//Usage: -postScript ApplyNames.java out/names_leon2sub.csv
//@category NT68503
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.SourceType;
import java.io.*;

public class ApplyNames extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 1) { println("ApplyNames: need a CSV path"); return; }
        File csv = new File(args[0]);
        if (!csv.isAbsolute())
            csv = new File(currentProgram.getExecutablePath()).getParentFile()
                    .getParentFile().toPath().resolve(args[0]).toFile();
        if (!csv.exists()) { println("ApplyNames: no such file " + csv); return; }

        int named = 0, created = 0, missing = 0;
        try (BufferedReader r = new BufferedReader(new FileReader(csv))) {
            String line = r.readLine();  // header
            while ((line = r.readLine()) != null) {
                String[] p = line.split(",", 2);
                if (p.length < 2) continue;
                Address a = currentProgram.getAddressFactory()
                        .getDefaultAddressSpace()
                        .getAddress(Long.parseLong(p[0].replace("0x", ""), 16));
                Function f = getFunctionAt(a);
                if (f == null) {
                    // The name is anchored on a prologue the analyser missed;
                    // create the function so the name has somewhere to live.
                    f = createFunction(a, p[1]);
                    if (f == null) { missing++; continue; }
                    created++;
                }
                f.setName(p[1], SourceType.USER_DEFINED);
                named++;
            }
        }
        println("RENAMED  : " + named + " functions (" + created
                + " newly created, " + missing + " unresolved)");
    }
}
