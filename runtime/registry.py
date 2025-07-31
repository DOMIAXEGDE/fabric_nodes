import subprocess, tempfile, textwrap, importlib, pkgutil, sys, os, time
from pathlib import Path
from types import ModuleType
from typing import Callable, Dict, Tuple

ExecutorFn = Callable[[str], Tuple[bool, str]]
PLUGIN_DIR = Path(__file__).parent / "plugins"
TIMEOUT = 5  # seconds – one place to change it!

class ExecutorRegistry:
    """Global store for all language executors."""
    def __init__(self) -> None:
        self._exec: Dict[str, ExecutorFn] = {}
        PLUGIN_DIR.mkdir(parents=True, exist_ok=True)

    # ---------- public API ----------
    def register(self, lang: str, fn: ExecutorFn) -> None:
        self._exec[lang.lower()] = fn

    def unregister(self, lang: str) -> None:
        self._exec.pop(lang.lower(), None)

    def list_languages(self):
        return sorted(self._exec)

    def has(self, lang: str) -> bool:
        return lang.lower() in self._exec

    def execute(self, code: str, lang: str) -> Tuple[bool, str]:
        fn = self._exec.get(lang.lower())
        if not fn:
            return False, f"No executor for {lang}. Create one from the ➕ menu!"
        return fn(code)

    # ---------- plugin loading ----------
    def load_plugins(self) -> None:
        """Import every *.py in plugins/ that defines `register`."""
        for mod_info in pkgutil.iter_modules([str(PLUGIN_DIR)]):
            full = f"runtime.plugins.{mod_info.name}"
            try:
                mod = importlib.import_module(full)
                if hasattr(mod, "register"):
                    mod.register(self)
            except Exception as e:
                print(f"[plugins] {full} failed: {e}")

    def hot_reload(self) -> None:
        """Re-import any plugin whose mtime has changed."""
        for mod in list(sys.modules.values()):
            if getattr(mod, "__file__", ""):
                p = Path(mod.__file__)
                if PLUGIN_DIR in p.parents and p.suffix == ".py":
                    mtime = p.stat().st_mtime
                    if mtime > getattr(mod, "__loaded_mtime__", 0):
                        try:
                            importlib.reload(mod)
                            mod.__loaded_mtime__ = mtime
                            print(f"[plugins] reloaded {p.name}")
                        except Exception as e:
                            print(f"[plugins] reload {p.name} failed: {e}")

