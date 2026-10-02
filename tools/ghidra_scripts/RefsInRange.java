//List every instruction whose reference or scalar operand falls in [lo, hi].
//Catches sethi/or data addresses that per-address RefsTo would miss when Ghidra
//attached the reference to a neighbouring byte.
//Usage: -postScript RefsInRange.java /abs/out.txt 0xLO 0xHI
//@category NT68503
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.scalar.Scalar;
import ghidra.program.model.symbol.Reference;
import java.io.*;

public class RefsInRange extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 3) throw new IllegalArgumentException("need out, lo, hi");
        long lo = Long.parseLong(args[1].replace("0x", ""), 16);
        long hi = Long.parseLong(args[2].replace("0x", ""), 16);
        int n = 0;
        try (PrintWriter w = new PrintWriter(new FileWriter(args[0]))) {
            InstructionIterator it = currentProgram.getListing().getInstructions(true);
            while (it.hasNext()) {
                Instruction ins = it.next();
                String hit = null;
                for (Reference r : ins.getReferencesFrom()) {
                    long t = r.getToAddress().getOffset();
                    if (t >= lo && t <= hi) { hit = "ref " + r.getReferenceType() + " " + r.getToAddress(); break; }
                }
                if (hit == null) {
                    for (int op = 0; op < ins.getNumOperands() && hit == null; op++)
                        for (Object o : ins.getOpObjects(op))
                            if (o instanceof Scalar) {
                                long v = ((Scalar) o).getUnsignedValue();
                                if (v >= lo && v <= hi) { hit = "scalar " + Long.toHexString(v); break; }
                            }
                }
                if (hit == null) continue;
                Function f = getFunctionContaining(ins.getAddress());
                w.println(ins.getAddress() + "  " + hit + "  "
                        + (f != null ? f.getEntryPoint().toString() : "<no function>")
                        + "  " + ins.toString().replace('\t', ' '));
                n++;
            }
            w.println("total: " + n);
        }
        println("REFSINRANGE: written -> " + args[0]);
    }
}
