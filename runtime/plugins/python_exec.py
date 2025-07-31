import runpy
import io
import contextlib
import threading

from runtime.constants import TIMEOUT

def _exec(code: str) -> tuple[bool, str]:
    buf = io.StringIO()

    def target():
        with contextlib.redirect_stdout(buf):
            runpy.run_path("<string>", {}, code)

    t = threading.Thread(target=target)
    t.start()
    t.join(TIMEOUT)
    if t.is_alive():
        return False, "⏱️ Timeout"
    return True, buf.getvalue()

def register(reg):
    reg.register("python", _exec)
