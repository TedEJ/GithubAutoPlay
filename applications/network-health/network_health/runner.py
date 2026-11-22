"""The one place where system commands are started.

Every check that needs a system command goes through a Runner. Tests replace
it with a fake that returns recorded, made-up output, so no test starts a real
command.
"""

from __future__ import annotations

import locale
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Sequence


@dataclass
class CommandResult:
    args: tuple[str, ...]
    returncode: int | None
    stdout: str = ""
    stderr: str = ""
    # None when the command ran, otherwise "not-found", "permission",
    # "timeout" or "os-error".
    error: str | None = None
    elapsed_s: float = 0.0


def default_encoding() -> str:
    """Console programs on Windows write in the OEM code page."""
    if sys.platform == "win32":
        return "oem"
    return locale.getpreferredencoding(False) or "utf-8"


class Runner:
    """Runs a command and never raises: problems come back in .error."""

    def run(
        self,
        args: Sequence[str],
        *,
        timeout: float = 30.0,
        encoding: str | None = None,
    ) -> CommandResult:
        args = tuple(args)
        enc = encoding or default_encoding()
        start = time.perf_counter()
        try:
            proc = subprocess.run(
                list(args),
                capture_output=True,
                stdin=subprocess.DEVNULL,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError:
            return CommandResult(args, None, error="not-found",
                                 elapsed_s=time.perf_counter() - start)
        except PermissionError:
            return CommandResult(args, None, error="permission",
                                 elapsed_s=time.perf_counter() - start)
        except subprocess.TimeoutExpired:
            return CommandResult(args, None, error="timeout",
                                 elapsed_s=time.perf_counter() - start)
        except OSError as exc:
            return CommandResult(args, None, stderr=str(exc), error="os-error",
                                 elapsed_s=time.perf_counter() - start)
        return CommandResult(
            args,
            proc.returncode,
            stdout=_decode(proc.stdout, enc),
            stderr=_decode(proc.stderr, enc),
            elapsed_s=time.perf_counter() - start,
        )


def _decode(data: bytes | None, encoding: str) -> str:
    if not data:
        return ""
    try:
        return data.decode(encoding, errors="replace")
    except LookupError:  # an encoding this Python does not know
        return data.decode("utf-8", errors="replace")
