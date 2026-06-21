from __future__ import annotations

import os
import signal
import subprocess

from .errors import ProxyError


def run(
    cmd: list[str],
    *,
    check: bool = True,
    capture: bool = False,
    isolate_signals: bool = False,
) -> subprocess.CompletedProcess[str]:
    if isolate_signals:
        proc = run_isolated(cmd, capture=capture)
    else:
        proc = subprocess.run(
            cmd,
            text=True,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None,
        )
    if check and proc.returncode != 0:
        rendered = " ".join(cmd)
        detail = ""
        if capture:
            detail = (proc.stderr or proc.stdout or "").strip()
        raise ProxyError(f"command failed ({proc.returncode}): {rendered} {detail}")
    return proc


def run_isolated(
    cmd: list[str],
    *,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.Popen(
        cmd,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate()
    except KeyboardInterrupt:
        terminate_process_group(proc)
        raise
    return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)


def terminate_process_group(proc: subprocess.Popen[str]) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    proc.wait()
