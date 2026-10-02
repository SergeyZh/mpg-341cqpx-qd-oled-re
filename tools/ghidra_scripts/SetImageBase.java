//Set the program image base. Usage: -postScript SetImageBase.java 0xA0060000
//@category NT68503
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;

public class SetImageBase extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 1) { println("SetImageBase: need a base address"); return; }
        Address base = currentProgram.getAddressFactory()
                .getDefaultAddressSpace().getAddress(args[0]);
        currentProgram.setImageBase(base, true);
        println("IMAGEBASE set to " + currentProgram.getImageBase());
    }
}
