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

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from runtime.registry import TIMEOUT  # shared timeout value

# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------

def _find_compiler() -> str | None:
    """Return the first available C++ compiler (g++ / clang++)."""
    for name in ("g++", "clang++"):
        path = shutil.which(name)
        if path:
            return path
    return None


def _compile_and_run(code: str) -> tuple[bool, str]:
    """Compile C++ source *code* and run the resulting program."""
    compiler = _find_compiler()
    if not compiler:
        return False, "No C++ compiler (g++ or clang++) found on your PATH."

    # Use an isolated temp directory
    with tempfile.TemporaryDirectory(prefix="cpp_exec_") as tmpdir:
        tmpdir = Path(tmpdir)
        src = tmpdir / "snippet.cpp"
        exe = tmpdir / ("snippet.exe" if os.name == "nt" else "snippet.out")

        # 1️⃣  write snippet.cpp
        src.write_text(code, encoding="utf-8")

        # 2️⃣  compile
        compile_cmd = [
            compiler,
            "-std=c++20",
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
            return False, f"❌ Compilation failed:\n{comp.stdout}{comp.stderr}"

        # 3️⃣  execute
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
# plugin entry-point
# ----------------------------------------------------------------------

def register(reg) -> None:
    """
    Called automatically by ExecutorRegistry.load_plugins() /
    hot_reload(). Registers the ``cpp`` language executor.
    """
    reg.register("cpp", _compile_and_run)
