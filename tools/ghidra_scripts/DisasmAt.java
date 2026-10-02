//Disassemble at explicit addresses without creating functions.
//Needed where Keil's switch helper (LCALL to ?C?CCASE followed by an inline
//jump table) hides the case targets from the analyser.
//Usage: -postScript DisasmAt.java 0x6e9a,0x6ea7,...
//@category NT68503
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;

public class DisasmAt extends GhidraScript {
    public void run() throws Exception {
        String[] addrs = getScriptArgs()[0].split(",");
        int ok = 0;
        for (String s : addrs) {
            s = s.trim();
            // "0xAAAA-0xBBBB" sweeps the range linearly, filling the gaps the
            // analyser left behind; a bare address disassembles just that spot.
            if (s.contains("-")) {
                String[] r = s.split("-");
                long from = Long.parseLong(r[0].substring(2), 16);
                long to = Long.parseLong(r[1].substring(2), 16);
                for (long p = from; p < to; p++) {
                    Address a = toAddr(p);
                    if (getInstructionAt(a) != null) continue;
                    try { if (disassemble(a)) ok++; } catch (Exception e) { }
                }
                continue;
            }
            Address a = toAddr(Long.parseLong(s.substring(2), 16));
            try { if (disassemble(a)) ok++; } catch (Exception e) { }
        }
        println("DISASM   : " + ok + "/" + addrs.length + " addresses");
        analyzeChanges(currentProgram);
        println("INSTRS   : " + currentProgram.getListing().getNumInstructions());
    }
}
