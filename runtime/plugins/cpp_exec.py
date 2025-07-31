"""
C++ language executor for the nodes.py plugin system
====================================================

• Looks for **g++** or **clang++** on PATH (in that order).
• Compiles user code with `-std=c++20 -O2 -pipe`, then executes the
  binary—all within the global TIMEOUT from runtime.registry.
• Returns the (success: bool, output: str) tuple expected by
  ExecutorRegistry.
"""

from __future__ import annotations

from runtime.compile_and_run import compile_and_run, _find


def _exec(code: str) -> tuple[bool, str]:
    cxx = _find(("g++", "clang++"))
    if not cxx:
        return False, "No C++ compiler found"
    cmd = [cxx, "-std=c++20", "-O2", "-pipe", code]
    return compile_and_run(".cpp", cmd)


# ----------------------------------------------------------------------
# plugin entry-point
# ----------------------------------------------------------------------

def register(reg) -> None:
    reg.register("cpp", _exec)
