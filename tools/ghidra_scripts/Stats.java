//Report function/instruction counts and name functions from debug strings.
//@category NT68503
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import ghidra.program.model.address.*;
import ghidra.program.model.symbol.*;
import ghidra.program.model.mem.*;

public class Stats extends GhidraScript {
    public void run() throws Exception {
        Listing l = currentProgram.getListing();
        int funcs = 0;
        for (Function f : l.getFunctions(true)) funcs++;
        long instrs = l.getNumInstructions();
        long defined = l.getNumDefinedData();
        println("PROGRAM  : " + currentProgram.getName());
        println("IMAGEBASE: " + currentProgram.getImageBase());
        println("FUNCTIONS: " + funcs);
        println("INSTRS   : " + instrs);
        println("DEFDATA  : " + defined);
        int strs = 0;
        for (Data d : l.getDefinedData(true))
            if (d.getDataType().getName().toLowerCase().contains("string")) strs++;
        println("STRINGS  : " + strs);
    }
}
