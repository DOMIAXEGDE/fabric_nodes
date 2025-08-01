from __future__ import annotations

from runtime.compile_and_run import compile_and_run, _find


def _exec(code: str) -> tuple[bool, str]:
    cxx = _find(("g++", "clang++"))
    if not cxx:
        return False, "No C++ compiler found"
    
    # 1. Append the source code to the command list.
    cmd = [cxx, "-std=c++20", "-O2", "-pipe", code]
    
    # 2. Call the helper with the corrected command list.
    return compile_and_run(".cpp", cmd)

def register(reg):
    reg.register("cpp", _exec)