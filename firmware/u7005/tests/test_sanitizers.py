import subprocess
from conftest import PROJECT


def test_address_and_undefined_sanitizers(tmp_path):
    exe = tmp_path/'fuzz'
    subprocess.run(['cc', '-std=c11', '-O1', '-g', '-fsanitize=address,undefined',
                    '-fno-sanitize-recover=all', '-I'+str(PROJECT/'include'),
                    *(str(PROJECT/p) for p in ['src/bridge.c','src/msc.c','tests/mock.c','tests/fuzz.c']),
                    '-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True,timeout=60)
