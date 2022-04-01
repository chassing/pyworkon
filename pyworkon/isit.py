import os
import platform
import sys
from pathlib import Path

# Linux
linux = platform.system().lower() == "linux"
linux_version = platform.release()

# Osx
osx = platform.system().lower() == "darwin"
osx_version = None
if osx:
    osx_version = platform.mac_ver()[0]

# Windows
windows = "win32" in str(sys.platform).lower()

XDG_CONFIG_HOME = Path(os.getenv("XDG_CONFIG_HOME")).expanduser() if os.getenv("XDG_CONFIG_HOME") else None
if not XDG_CONFIG_HOME:
    XDG_CONFIG_HOME = Path.home()
    if linux:
        XDG_CONFIG_HOME = XDG_CONFIG_HOME / ".config"
    if osx:
        XDG_CONFIG_HOME = XDG_CONFIG_HOME / "Library" / "Application Support"

XDG_CACHE_HOME = Path(os.getenv("XDG_CACHE_HOME")).expanduser() if os.getenv("XDG_CACHE_HOME") else None
if not XDG_CACHE_HOME:
    XDG_CACHE_HOME = Path.home()
    if linux:
        XDG_CACHE_HOME = XDG_CACHE_HOME / ".cache"
    if osx:
        XDG_CACHE_HOME = XDG_CACHE_HOME / "Library" / "Caches"
