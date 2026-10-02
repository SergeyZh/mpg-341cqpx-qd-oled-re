// Rebuild reachable 8051 listing for the unchanged FW.023/.034/.037 USB AUX image.
// Usage: -postScript AuxUsbListing.java /abs/out.asm
// Handles Keil inline stores, switches and this image's computed jump tables.
// Changes analysis metadata only; never changes firmware bytes.
//@category NT68503
import ghidra.app.script.GhidraScript;
import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.data.ByteDataType;
import java.util.*;
import java.security.MessageDigest;

public class AuxUsbListing extends GhidraScript {
    private int u8(long p) throws Exception { return getByte(toAddr(p)) & 255; }
    private int be16(long p) throws Exception { return (u8(p) << 8) | u8(p+1); }
    private String imageHash() throws Exception {
        byte[] b = new byte[0xe552];
        if (currentProgram.getMemory().getBytes(toAddr(0), b) != b.length)
            throw new IllegalStateException("Incomplete AUX image");
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(b));
    }
    public void run() throws Exception {
        if (getScriptArgs().length != 1)
            throw new IllegalArgumentException("Usage: AuxUsbListing.java /abs/out.asm");
        String before = imageHash();
        if (!before.equals("bed2d9922e6e98990573dee3066d5871806e4ecd703a48d184c2135be128e592"))
            throw new IllegalArgumentException("Not the verified USB AUX image");
        if (u8(0) != 2 || be16(1) != 0xd426 || u8(0x34ed) != 0xa8)
            throw new IllegalArgumentException("Expected USB AUX image at CODE:0000");
        clearListing(toAddr(0), toAddr(0xe551));
        for (Function f : currentProgram.getFunctionManager().getFunctions(true))
            f.setNoReturn(false);
        ArrayDeque<Long> todo = new ArrayDeque<>();
        Set<Long> seen = new HashSet<>();
        todo.add(0L);
        int inline = 0, switches = 0;
        while (!todo.isEmpty() && !monitor.isCancelled()) {
            long p = todo.removeFirst();
            if (p < 0 || p >= 0xe552 || !seen.add(p)) continue;
            Address a = toAddr(p);
            if (getDataAt(a) != null) throw new IllegalStateException("Flow into data: " + a);
            if (getInstructionAt(a) == null) {
                DisassembleCommand cmd = new DisassembleCommand(a, new AddressSet(a, a), false);
                if (!cmd.applyTo(currentProgram, monitor))
                    throw new IllegalStateException("Cannot decode: " + a);
            }
            Instruction ins = getInstructionAt(a);
            if (ins == null) throw new IllegalStateException("Missing instruction: " + a);
            long next = p + ins.getLength();
            if (u8(p) == 0x12 && be16(p+1) == 0x34ed) {
                for (long q=next; q<next+4; q++) createData(toAddr(q), new ByteDataType());
                ins.setFallThrough(toAddr(next+4));
                todo.add(0x34edL); todo.add(next+4); inline++;
            } else if (u8(p) == 0x12 && be16(p+1) == 0x353e) {
                long q = next;
                while (be16(q) != 0) {
                    int target = be16(q);
                    if (target >= 0xe552) throw new IllegalStateException("Bad switch at " + a);
                    todo.add((long) target); q += 3;
                    if (q-next > 768) throw new IllegalStateException("Unterminated switch");
                }
                todo.add((long) be16(q+2));
                for (long d=next; d<q+4; d++) createData(toAddr(d), new ByteDataType());
                ins.setFallThrough(null); todo.add(0x353eL); switches++;
            } else if (p == 0x53ad) {
                // bRequest dispatcher: twelve three-byte LJMP instructions.
                for (long q=0x53ae; q<0x53d2; q+=3) {
                    if (u8(q) != 2) throw new IllegalStateException("Bad control switch");
                    todo.add(q);
                }
            } else if (p == 0x3178) {
                // Keil generic memcpy: sixteen two-byte SJMP entries.
                for (long q=0x30d3; q<0x30f3; q+=2) todo.add(q);
            } else {
                for (Address flow : ins.getFlows()) todo.add(flow.getOffset());
                // Calls return via registers/stack tricks which Ghidra cannot model.
                if (ins.getFlowType().isCall() || ins.getFallThrough() != null) todo.add(next);
            }
        }
        println("AUX_REACHABLE instructions=" + seen.size() + " inline=" + inline + " switches=" + switches);
        if (!before.equals(imageHash())) throw new IllegalStateException("Image bytes changed");
        println("AUX_BYTES_UNCHANGED SHA256=" + before);
        runScript("DumpAsm.java", new String[]{getScriptArgs()[0], "0x0", "0xe552"});
    }
}
