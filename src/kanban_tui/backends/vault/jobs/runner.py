from __future__ import annotations

import os
import subprocess
from collections.abc import Callable

Runner = Callable[[list[str], dict[str, str], float], tuple[int, str, str]]
"""Runs argv with extra environment variables over os.environ and a timeout in
seconds, returning (exit code, stdout, stderr). Raises subprocess.TimeoutExpired."""


def run_command(
    argv: list[str], env: dict[str, str], timeout: float
) -> tuple[int, str, str]:
    result = subprocess.run(
        argv,
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return result.returncode, result.stdout, result.stderr
