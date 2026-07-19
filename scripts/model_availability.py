"""On-demand readiness checks for Cornell KB media models.

This module deliberately does not register services, create scheduled tasks, or
modify Windows Startup. Ollama is launched only after a request finds the
configured endpoint unavailable. Whisper is an in-process runtime, so its
"start" operation is simply loading the requested model when transcription is
actually requested.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from typing import Any, Callable

DEFAULT_SSH_TARGET = os.environ.get(
    "CORNELL_KB_OLLAMA_SSH_TARGET", "31163@100.104.205.105"
)
DEFAULT_REMOTE_EXECUTABLE = os.environ.get(
    "CORNELL_KB_OLLAMA_REMOTE_EXE",
    r"C:\Users\31163\AppData\Local\Programs\Ollama\ollama.exe",
)

# Keep the SSH PTY alive for the duration of the current pipeline process.
# The list is intentionally process-local; it is not a service registry.
_OLLAMA_PROCESSES: list[subprocess.Popen[Any]] = []


def _tags_url(ollama_url: str) -> str:
    if "/api/" in ollama_url:
        return ollama_url.split("/api/", 1)[0] + "/api/tags"
    return ollama_url.rstrip("/") + "/api/tags"


def _model_matches(requested: str, available: dict[str, Any]) -> bool:
    names = {available.get("name"), available.get("model")}
    names.discard(None)
    if requested in names:
        return True
    return f"{requested}:latest" in names


def probe_ollama(ollama_url: str, model: str | None = None, timeout: float = 5) -> bool:
    """Return whether Ollama is reachable and, optionally, has ``model``."""
    request = urllib.request.Request(_tags_url(ollama_url), method="GET")
    # Local/Tailscale service probes must not depend on the machine's HTTP proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, urllib.error.URLError):
        return False

    if model is None:
        return True
    return any(_model_matches(model, item) for item in payload.get("models", []))


def start_ollama(
    ssh_target: str = DEFAULT_SSH_TARGET,
    remote_executable: str = DEFAULT_REMOTE_EXECUTABLE,
) -> subprocess.Popen[Any]:
    """Start Ollama in a PTY-backed SSH process, without persistent auto-start.

    Windows Ollama can fail when launched with ``Start-Process`` from an SSH
    session because the GUI initialization path is used. A foreground
    ``ollama serve`` behind ``ssh -tt`` uses the server path reliably. The
    returned process owns that temporary connection and remains available for
    the current pipeline run.
    """
    remote_command = f'set OLLAMA_HOST=0.0.0.0&&"{remote_executable}" serve'
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    process = subprocess.Popen(
        [
            "ssh",
            "-tt",
            "-o",
            "ConnectTimeout=10",
            "-o",
            "ServerAliveInterval=30",
            ssh_target,
            remote_command,
        ],
        # A live pipe keeps the remote PTY and foreground `ollama serve` alive.
        # It is closed naturally when this pipeline process exits.
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    _OLLAMA_PROCESSES.append(process)
    return process


def ensure_ollama_available(
    ollama_url: str,
    *,
    model: str | None = None,
    timeout: float = 5,
    startup_timeout: float = 30,
    poll_interval: float = 1,
    ssh_target: str = DEFAULT_SSH_TARGET,
    remote_executable: str = DEFAULT_REMOTE_EXECUTABLE,
    probe: Callable[..., bool] | None = None,
    starter: Callable[..., Any] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Probe Ollama and start it on demand if it is unavailable.

    ``probe`` and ``starter`` are injectable so offline tests never contact a
    real service or spawn SSH. No model is downloaded by this function.
    """
    probe = probe or probe_ollama
    starter = starter or start_ollama

    if probe(ollama_url, model, timeout):
        return {"available": True, "started": False, "model": model}

    starter(ssh_target=ssh_target, remote_executable=remote_executable)
    deadline = time.monotonic() + startup_timeout
    while True:
        if probe(ollama_url, model, timeout):
            return {"available": True, "started": True, "model": model}
        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"Ollama did not become available at {ollama_url}"
                + (f" with model {model!r}" if model else "")
                + ". The on-demand SSH launch was attempted; no auto-start was configured."
            )
        sleep_fn(max(0.05, poll_interval))
