from __future__ import annotations
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable, Tuple

from runtime.constants import TIMEOUT


def _find(progs: Iterable[str]) -> str | None:
    for p in progs:
        exe = shutil.which(p)
        if exe:
            return exe
    return None


def compile_and_run(src_suffix: str, cmd: list[str], run_argv: list[str] | None = None) -> Tuple[bool, str]:
    """Compile and run a program with TIMEOUT."""
    run_argv = run_argv or []
    with tempfile.TemporaryDirectory(prefix="exec_") as td:
        td_path = Path(td)
        src = td_path / f"snippet{src_suffix}"
        exe = td_path / ("a.exe" if os.name == "nt" else "a.out")
        src.write_text(cmd[-1], encoding="utf-8")
        cmd[-1] = str(src)
        cmd.extend(["-o", str(exe)])
        try:
            comp = subprocess.run(cmd, text=True, capture_output=True, timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            return False, f"⏱️ Compilation exceeded {TIMEOUT}s"
        if comp.returncode:
            return False, comp.stdout + comp.stderr
        try:
            run = subprocess.run([str(exe), *run_argv], text=True, capture_output=True, timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            return False, f"⏱️ Execution exceeded {TIMEOUT}s"
        ok = run.returncode == 0
        return ok, run.stdout if ok else run.stderr
