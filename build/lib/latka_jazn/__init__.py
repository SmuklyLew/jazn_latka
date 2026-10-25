"""Łatka Jaźń active runtime package."""

from .core.loopback_proxy import ensure_loopback_proxy_bypass as _ensure_loopback_proxy_bypass

_ensure_loopback_proxy_bypass()
del _ensure_loopback_proxy_bypass

from .version import PACKAGE_VERSION, PACKAGE_VERSION_FULL

__version__ = PACKAGE_VERSION
__version_full__ = PACKAGE_VERSION_FULL
