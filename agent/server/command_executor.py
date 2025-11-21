import subprocess
from typing import Tuple

def run_veracli(args: list[str]) -> Tuple[str, str, int]:
    """
    Executes: veracli <args> and returns (stdout, stderr, exit_code)
    """
    try:
        cmd = ["veracli"] + args
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = proc.communicate()
        return stdout, stderr, proc.returncode

    except FileNotFoundError:
        return "", "veracli not found in PATH", 127