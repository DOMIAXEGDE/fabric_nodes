"""
C language executor for the nodes.py plugin system
==================================================

• Creates a temporary *.c* file, compiles it with **gcc or clang**,
  then executes the resulting binary–all inside the global TIMEOUT.
• Returns the standard (success: bool, output: str) tuple expected by
  ExecutorRegistry.
• C11, -O2, and -pipe are used by default; tweak as needed.
"""

from __future__ import annotations

from runtime.compile_and_run import compile_and_run, _find


def _exec(code: str) -> tuple[bool, str]:
    cc = _find(("gcc", "clang"))
    if not cc:
        return False, "No C compiler found"
    cmd = [cc, "-std=c11", "-O2", "-pipe", code]
    return compile_and_run(".c", cmd)


# ----------------------------------------------------------------------
# Plugin entry-point
# ----------------------------------------------------------------------

def register(reg) -> None:
    reg.register("c", _exec)
