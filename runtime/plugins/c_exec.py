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

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

# Pull the sandbox timeout from the core runtime
from runtime.registry import TIMEOUT

# ----------------------------------------------------------------------
# Internal helpers
# ----------------------------------------------------------------------

def _find_compiler() -> str | None:
    """Return the first C compiler (gcc/clang) found on PATH."""
    for name in ("gcc", "clang"):
        path = shutil.which(name)
        if path:
            return path
    return None


def _compile_and_run(code: str) -> tuple[bool, str]:
    """Compile *code* (C source) and execute, respecting TIMEOUT."""
    compiler = _find_compiler()
    if not compiler:
        return False, "No C compiler (gcc or clang) found on your system PATH."

    # Use an ephemeral temp dir so nothing is left behind even if we crash
    with tempfile.TemporaryDirectory(prefix="c_exec_") as tmpdir:
        tmpdir = Path(tmpdir)
        src = tmpdir / "snippet.c"
        exe = tmpdir / ("snippet.exe" if os.name == "nt" else "snippet.out")

        # 1️⃣  Write the user’s C code
        src.write_text(code, encoding="utf-8")

        # 2️⃣  Compile
        compile_cmd = [
            compiler,
            "-std=c11",
            "-O2",
            "-pipe",
            str(src),
            "-o",
            str(exe),
        ]
        try:
            comp = subprocess.run(
                compile_cmd,
                text=True,
                capture_output=True,
                timeout=TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return False, f"⏱️ Compilation exceeded {TIMEOUT}s timeout."

        if comp.returncode != 0:
            # Pipe both stdout and stderr back for better diagnostics
            return False, f"❌ Compilation failed:\n{comp.stdout}{comp.stderr}"

        # 3️⃣  Execute the freshly-built binary
        try:
            run = subprocess.run(
                [str(exe)],
                text=True,
                capture_output=True,
                timeout=TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return False, f"⏱️ Execution exceeded {TIMEOUT}s timeout."

        if run.returncode != 0:
            return False, f"💥 Runtime error (exit {run.returncode}):\n{run.stderr}"

        return True, run.stdout or "(program exited with no output)"


# ----------------------------------------------------------------------
# Plugin entry-point
# ----------------------------------------------------------------------

def register(reg) -> None:
    """
    nodes.py plugin hook.

    Called automatically by ExecutorRegistry.load_plugins() / hot_reload().
    Registers the ``c`` language executor.
    """
    reg.register("c", _compile_and_run)
