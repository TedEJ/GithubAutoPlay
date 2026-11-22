"""Choose the platform layer for the operating system the tool runs on."""

from __future__ import annotations

import sys

from .base import NetworkPlatform


class UnsupportedPlatform(Exception):
    pass


def get_platform(system: str | None = None, runner=None) -> NetworkPlatform:
    system = system or sys.platform
    if system == "win32":
        from .windows import WindowsPlatform
        return WindowsPlatform(runner)
    raise UnsupportedPlatform(
        "network-health runs on Windows for now. Linux support is planned "
        "in a later issue (#152)."
    )


__all__ = ["NetworkPlatform", "UnsupportedPlatform", "get_platform"]
