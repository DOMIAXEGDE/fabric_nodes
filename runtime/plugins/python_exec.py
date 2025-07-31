import subprocess, tempfile, sys
from runtime.registry import TIMEOUT

def _run_temp(code: str) -> tuple[bool, str]:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".py")
    try:
        tmp.write(code.encode())
        tmp.close()
        res = subprocess.run(
            [sys.executable, tmp.name],
            text=True,
            capture_output=True,
            timeout=TIMEOUT
        )
        return (res.returncode == 0, res.stdout if res.returncode == 0 else res.stderr)
    except subprocess.TimeoutExpired:
        return False, "Execution timed out"
    finally:
        try: __import__("os").remove(tmp.name)
        except: pass

def register(reg):
    reg.register("python", _run_temp)
