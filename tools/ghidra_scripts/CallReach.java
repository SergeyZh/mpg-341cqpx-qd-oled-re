//Breadth-first call graph from root functions; report which targets are reachable and by which path.
//Uses Ghidra's call references (Function.getCalledFunctions), so resolved computed calls count too.
//Usage: -postScript CallReach.java /abs/out.txt 0xROOT1,0xROOT2 0xTARGET1,0xTARGET2,...
//@category NT68503
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import java.io.*;
import java.util.*;

public class CallReach extends GhidraScript {
    private Address addr(String s) {
        return currentProgram.getAddressFactory().getDefaultAddressSpace()
                .getAddress(Long.parseLong(s.trim().replace("0x", ""), 16));
    }

    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 3) throw new IllegalArgumentException("need out, roots, targets");
        Map<Function, Function> parent = new LinkedHashMap<>();
        ArrayDeque<Function> queue = new ArrayDeque<>();
        try (PrintWriter w = new PrintWriter(new FileWriter(args[0]))) {
            for (String r : args[1].split(",")) {
                Function f = getFunctionAt(addr(r));
                if (f == null) { w.println("ROOT " + r + " has no function"); continue; }
                parent.put(f, null);
                queue.add(f);
            }
            while (!queue.isEmpty()) {
                Function f = queue.poll();
                for (Function c : f.getCalledFunctions(monitor)) {
                    if (parent.containsKey(c)) continue;
                    parent.put(c, f);
                    queue.add(c);
                }
            }
            w.println("reachable functions: " + parent.size());
            for (String t : args[2].split(",")) {
                Function f = getFunctionAt(addr(t));
                if (f == null) { w.println("TARGET " + t + " has no function"); continue; }
                if (!parent.containsKey(f)) { w.println("TARGET " + t + " not reachable"); continue; }
                StringBuilder path = new StringBuilder();
                for (Function p = f; p != null; p = parent.get(p))
                    path.insert(0, " -> " + p.getEntryPoint());
                w.println("TARGET " + t + " REACHABLE:" + path);
            }
            w.println("functions:");
            for (Function f : parent.keySet())
                w.println("    " + f.getEntryPoint() + "  " + f.getName());
        }
        println("CALLREACH: written -> " + args[0]);
    }
}
