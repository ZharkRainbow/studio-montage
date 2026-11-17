"""Run a local tool while reading its output live, so long encodes report real progress."""
from __future__ import annotations

from collections import deque
import os
import queue
import signal
import re
import subprocess
import threading
from typing import Callable, Sequence

_FFMPEG_TIME = re.compile(r"^out_time_(?:us|ms)=(\d+)$")
_WHISPER_PROGRESS = re.compile(r"progress\s*=\s*(\d+)%")
_KEY_VALUE = re.compile(r"^[a-z_0-9]+=")


def _descendants(pid: int) -> list[int]:
    """Every process started under `pid`, children first seen by `ps`, whatever their process group."""
    try:
        table = subprocess.run(["ps", "-A", "-o", "pid=,ppid="], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    children: dict[int, list[int]] = {}
    for row in table.splitlines():
        parts = row.split()
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            children.setdefault(int(parts[1]), []).append(int(parts[0]))
    found, stack = [], [pid]
    while stack:
        for child in children.get(stack.pop(), []):
            found.append(child)
            stack.append(child)
    return found


def _stop_tree(process: subprocess.Popen) -> None:
    """Stop a tool that drives a browser, with every process it started.

    Browser drivers put Chrome in its own process group and relaunch it when it dies: the driver is
    frozen first so nothing respawns, then the whole tree is killed.
    """
    try:
        os.kill(process.pid, signal.SIGSTOP)
    except ProcessLookupError:
        return
    for pid in [*reversed(_descendants(process.pid)), process.pid]:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def stream(
    args: Sequence[object],
    check: Callable[[], None],
    on_line: Callable[[str], None],
    *,
    error: type[Exception] = RuntimeError,
    label: str = "commande",
    process_group: bool = False,
    cwd: object | None = None,
) -> None:
    command = [str(value) for value in args]
    check()
    try:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1,
                                   start_new_session=process_group, cwd=None if cwd is None else str(cwd))
    except OSError as exc:
        raise error(f"Impossible de lancer {command[0]} : {exc}") from exc
    lines: queue.Queue[str] = queue.Queue()
    tail: deque[str] = deque(maxlen=12)

    def pump(pipe):
        for line in iter(pipe.readline, ""):
            lines.put(line)
        pipe.close()

    pumps = [threading.Thread(target=pump, args=(pipe,), daemon=True) for pipe in (process.stdout, process.stderr)]
    for thread in pumps:
        thread.start()
    try:
        while True:
            check()
            try:
                line = lines.get(timeout=0.2).rstrip()
            except queue.Empty:
                if process.poll() is not None and not any(thread.is_alive() for thread in pumps) and lines.empty():
                    break
                continue
            if line:
                tail.append(line)
                on_line(line)
    except BaseException:
        if process_group:
            _stop_tree(process)
        else:
            process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        raise
    code = process.wait()
    if code:
        detail = " | ".join(line for line in tail if not _KEY_VALUE.match(line))[-1200:]
        raise error(f"{label} a échoué ({code}) : {detail or 'erreur inconnue'}")


def ffmpeg_fraction(line: str, duration: float) -> float | None:
    """Fraction of the output written, from a `-progress pipe:1` line; None for other lines."""
    match = _FFMPEG_TIME.match(line)
    if not match or duration <= 0:
        return None
    return max(0.0, min(1.0, int(match.group(1)) / 1_000_000 / duration))


def whisper_fraction(line: str) -> float | None:
    match = _WHISPER_PROGRESS.search(line)
    return max(0.0, min(1.0, int(match.group(1)) / 100)) if match else None
