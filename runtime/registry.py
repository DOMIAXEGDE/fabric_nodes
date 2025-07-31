import importlib
import importlib.metadata as md
import time
from types import ModuleType
from typing import Callable, Dict, Tuple, Optional

from runtime.constants import ENTRYPOINT_GROUP

ExecutorFn = Callable[[str], Tuple[bool, str]]
_THROTTLE = 0.25  # seconds


class ExecutorRegistry:
    """Global store for language executors."""

    def __init__(self) -> None:
        self._exec: Dict[str, ExecutorFn] = {}
        self._last_tick = 0.0
        self._discover()

    # ---------- public API ----------
    def register(self, lang: str, fn: ExecutorFn) -> None:
        self._exec[lang.lower()] = fn

    def unregister(self, lang: str) -> None:
        self._exec.pop(lang.lower(), None)

    def list_languages(self):
        return sorted(self._exec)

    def has(self, lang: str) -> bool:
        return lang.lower() in self._exec

    def get(self, lang: str) -> Optional[ExecutorFn]:
        return self._exec.get(lang.lower())

    def execute(self, code: str, lang: str) -> Tuple[bool, str]:
        fn = self.get(lang)
        if not fn:
            return False, f"No executor for {lang}. Install a plugin."
        return fn(code)

    # ---------- discovery ----------
    def _discover(self) -> None:
        for ep in md.entry_points(group=ENTRYPOINT_GROUP):
            if ep.name in self._exec:
                continue
            try:
                mod: ModuleType = ep.load()
                if hasattr(mod, "register"):
                    mod.register(self)
            except Exception as e:
                print(f"[exec] {ep.name} failed: {e}")

    def tick(self) -> None:
        now = time.perf_counter()
        if now - self._last_tick > _THROTTLE:
            self._discover()
            self._last_tick = now


REGISTRY = ExecutorRegistry()
