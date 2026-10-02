#!/bin/bash
# Import the firmware regions into Ghidra projects with the right processor and
# load address. Run tools/fwmap.py -o out/ first to produce the region files.
#
#   tools/ghidra_import.sh [region...]      # default: all
#
# Ghidra 12 needs JDK 21+; the JetBrains runtime bundled with IntelliJ is 25 and
# works, so use it rather than installing a second JDK.
set -euo pipefail
cd "$(dirname "$0")/.."

GHIDRA="${GHIDRA:-$HOME/ghidra_12.0.2_PUBLIC}"
PROJ="${PROJ:-$PWD/ghidra}"
FW="${FW:-$PWD/MSI_MPG_341CQPX_QD-OLED_FW.037_0225.bin}"
JBR="${JBR:-$HOME/Applications/IntelliJ IDEA.app/Contents/jbr/Contents/Home}"
[ -d "$JBR" ] && export JAVA_HOME="$JBR"

mkdir -p "$PROJ"

# name | region file | processor | base address | names CSV (optional)
#
# leon2-sub base 0xA0060000 is established three ways: the trap table sits at
# the region start and its first handler resolves to 0xA00602C0; 68% of
# sethi+jmp targets land on function starts (next candidate: 4%); and the
# pointer table at 0x0A6000 holds 0xA00Axxxx values that map onto the Leon2S
# string area.
#
# leon2-main is linked at 0 with address 0 sitting at file offset 0x108000, so
# it is imported as the flash tail from there rather than as a cut-out region.
# Found by histogramming (function start - sethi/jmp target): 61% of targets
# land on function starts, next candidate 1%. Confirmed by disassembly --
# `sethi 0x577, %o2; or %o2, 0, %o0` builds 0x15DC00, exactly the address of
# the "OLED set lum mode" string under this mapping.
IMAGES=(
  "stbc-8051|out/region_000000_001900.bin|8051:BE:16:default|0x0000|"
  "stbc-main-8051|out/region_010000_01f100.bin|8051:BE:16:default|0x0000|"
  # STBC AUX (partition id=0x02) is the USB/ISP agent. It has no interrupt
  # table -- address 0 is a bare LJMP to main -- so seeding the usual 8051
  # vectors would disassemble ordinary code as handlers; seed 0 and main.
  "stbc-aux-8051|out/stbc_aux_020000.bin|8051:BE:16:default|0x0000||0x0,0xd426"
  # Partition id=0x03 is Tensilica Xtensa, little-endian -- not 8051 as the
  # byte-density heuristic first suggested. Xtensa:LE decodes 13885
  # instructions here, Xtensa:BE only 103. Base 0x40000000 comes from the
  # section table at file 0x3AC38, whose last section ends exactly at the
  # partition size (0x4000D8DC); see docs/tensilica.md. AddTensDram.java adds
  # the DRAM blocks that table describes -- without them nothing resolves.
  "tensilica|out/region_030000_03d900.bin|Xtensa:LE:32:default|0x40000000|names/tensilica_ldc.csv"
  "leon2-sub|out/region_050000_0a5600.bin|sparc:BE:32:default|0xA0060000|out/names_leon2sub.csv"
  "part0b|out/region_0b0000_0cf500.bin|sparc:BE:32:default|0x9F1B0000|names/part0b.csv"
  # Partition id=0x0D is the scaler service runtime.  A live FW.034 `mem`
  # dump at 0xA002F770 matches file offset 0x0D7770 after reversing the bytes
  # printed inside each 32-bit word, fixing the load base at 0xA0028000.  Its
  # trap table independently jumps to handlers in the 0xA0029xxx range.
  # Besides reset/trap handlers, seed every service-runtime entry exported to
  # FW.037 Leon2 Main.  Those calls cross raw-program boundaries, so Ghidra
  # cannot discover them by itself.  Addresses after 0xA002A878 move in FW.034;
  # see docs/scaler-service-runtime.md before applying an address to that build.
  "scaler-service|out/region_0d0000_0d8100.bin|sparc:BE:32:default|0xA0028000|names/scaler_service_fw037.csv|0x0,0x1000,0x10ec,0x1210,0x1220,0x1244,0x1278,0x12d0,0x1328,0x1388,0x1460,0x15a4,0x1820,0x1858,0x192c,0x1964,0x2878,0x2e5c,0x31e8,0x355c,0x392c,0x3c80,0x3f20,0x3f98,0x4054,0x4060,0x406c,0x42d4,0x43fc,0x4508,0x485c,0x4af4,0x4cdc,0x4fa4,0x5040,0x538c,0x5398,0x60a8,0x61c8,0x620c,0x64a0,0x64e8,0x6568,0x6f1c,0x7770,0x78cc,0x7c54,0x7d00,0x7fb8"
  "leon2-main|out/leon2main_108000.bin|sparc:BE:32:default|0x0|out/names_leon2main.csv"
  # U7005 is a separate chip, not part of the scaler image: Nuvoton NUC1261,
  # Cortex-M0, its APROM read out over SWD (docs/mcu-u7005.md). Linked at 0
  # with a normal Cortex-M vector table there, so the seeds below are the
  # handler addresses out of that table (bit 0 cleared -- they are Thumb).
  # The Cortex language variant defaults to TMode=1, so no context juggling.
  "u7005|flash/u7005_aprom.bin|ARM:LE:32:Cortex|0x0|names/u7005_boot.csv|0xcc,0xe4,0x100,0x120,0x124,0x126,0x128,0x12a,0x2484,0x24b0,0x3e50,0x55cc,0x5990,0x5e08,0x2000278c,0x2000279c,0x200027ac,0x200027bc,0x200027cc,0x20002814,0x2000286c,0x200028a0,0x200028d0,0x2000291c,0x20002930,0x20002944,0x200029e4,0x20002e98,0x20002ef4,0x20002f34,0x20002f74,0x20002fcc,0x2000308c,0x200030c4,0x20003586"
  # Historical AHB read, NOT yet a verified physical LDROM dump. This import
  # preserves absolute low-address literals; CBS=01 executes the selected
  # boot region at zero. See docs/u7005-ldrom.md. Offset 0xa4 is vector data,
  # not an instruction entry; the C runtime starts at 0xcc.
  "u7005-ldrom-ahb|flash/u7005_ldrom.bin|ARM:LE:32:Cortex|0x100000||0xcc,0x100,0x220"
  # Physical FMC dump, verified twice. CBS=01 executes LDROM at zero;
  # vectors and absolute pointers are linked at zero, NOT at 0x100000.
  "u7005-ldrom|flash/u7005_ldrom_fmc.bin|ARM:LE:32:Cortex|0x0|names/u7005_ldrom_v15.csv|0xc0,0xd4,0xf4,0xf6,0xf8,0xfa,0xfc,0xfe,0x144,0x30c,0x848,0xd08,0xd18"
)

for entry in "${IMAGES[@]}"; do
  IFS='|' read -r name file proc base names seed_override <<<"$entry"
  if [ $# -gt 0 ] && [[ ! " $* " =~ " $name " ]]; then continue; fi
  if [ ! -f "$file" ]; then
    echo "!! missing $file -- run tools/fwmap.py -o out/ first" >&2
    continue
  fi
  echo "== importing $name ($proc @ $base)"
  # A raw binary has no entry point, so the 8051 images disassemble to nothing
  # until the reset and interrupt vectors are seeded explicitly.
  case "$proc" in
    8051*) seed="8051" ;;
    *)     seed="" ;;
  esac
  [ -n "$seed_override" ] && seed="$seed_override"
  # The Tensilica image needs its DRAM blocks, and it needs them before
  # analysis: its strings, literal pool and .data are copied there and l32r
  # addresses them by their DRAM addresses. The blocks sit at absolute
  # addresses, so the base has to be set first -- setImageBase(commit) shifts
  # every block along with the image and would drag the DRAM blocks with it.
  rebase=(-postScript SetImageBase.java "$base")
  extra=()
  if [ "$name" = "tensilica" ]; then
    rebase=(-preScript SetImageBase.java "$base")
    extra=(-preScript AddTensDram.java "$FW")
  fi
  # The Cortex-M image is linked at 0, so SetImageBase 0x0 is a no-op; what it
  # does need is the SRAM and peripheral windows before analysis, or every MMIO
  # access decompiles as a bare constant.
  if [ "$name" = "u7005" ]; then
    extra=(-preScript AddCortexMem.java 0xcb00 0x20002600 0x1100)
  fi
  if [ "$name" = "u7005-ldrom-ahb" ]; then
    rebase=(-preScript SetImageBase.java "$base")
  fi
  if [ "$name" = "u7005-ldrom" ]; then
    extra=(-preScript AddCortexMem.java 0xf48 0x20000000 0xa4)
  fi
  # -loader-baseAddr is silently ignored for a raw binary here, so the base is
  # applied afterwards by SetImageBase.java instead.
  "$GHIDRA/support/analyzeHeadless" "$PROJ" nt68503 \
      -import "$file" -processor "$proc" -loader BinaryLoader \
      -overwrite -analysisTimeoutPerFile 900 \
      -scriptPath "$PWD/tools/ghidra_scripts" \
      "${rebase[@]}" ${extra[@]+"${extra[@]}"} \
      ${seed:+-postScript AddEntries.java "$seed"} \
      ${names:+-postScript ApplyNames.java "$PWD/$names"} \
      -postScript Stats.java \
      2>&1 | grep -viE "GhydraMCP|Module manifest|Invalid line" \
           | grep -E "IMAGEBASE|DRAMBLOCKS|FUNCTIONS|INSTRS|STRINGS|RENAMED|SEEDED|AFTERSEED|ERROR"
done
