from __future__ import annotations

from runtime.compile_and_run import compile_and_run, _find


def _exec(code: str) -> tuple[bool, str]:
    cc = _find(("gcc", "clang"))
    if not cc:
        return False, "No C compiler found"
    
    # 1. Append the source code to the command list.
    cmd = [cc, "-std=c11", "-O2", "-pipe", code]
    
    # 2. Call the helper with the corrected command list.
    return compile_and_run(".c", cmd)

def register(reg):
    reg.register("c", _exec)