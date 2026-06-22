"""Shared async utilities."""

from __future__ import annotations

import asyncio
import subprocess
from typing import Any


async def run_cmd(
    *cmd: str,
    check: bool = True,
    **kwargs: Any,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess command asynchronously.

    Drop-in async replacement for subprocess.run() with capture_output=True, text=True.
    """
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        **kwargs,
    )
    stdout_bytes, stderr_bytes = await proc.communicate()
    if check and proc.returncode:
        raise subprocess.CalledProcessError(
            proc.returncode, list(cmd), stdout_bytes, stderr_bytes
        )
    return subprocess.CompletedProcess(
        args=list(cmd),
        returncode=proc.returncode or 0,
        stdout=stdout_bytes.decode() if stdout_bytes else "",
        stderr=stderr_bytes.decode() if stderr_bytes else "",
    )
