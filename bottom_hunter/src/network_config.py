"""Centralized network settings for BottomHunter.

This module configures all HTTP clients (requests, urllib) to bypass any
system proxy by default. System proxies (Clash, etc.) are unnecessary
for most public market-data endpoints. If a proxy is explicitly needed,
set BOTTOM_HUNTER_USE_PROXY=1 before starting.
"""

from __future__ import annotations

import os
from typing import Any

# We explicitly disable proxies for all public market-data requests.
# This prevents local proxies (Clash, etc.) from blocking domestic
# providers like Eastmoney or Tencent. Set BOTTOM_HUNTER_USE_PROXY=1
# instead of relying on HTTP(S)_PROXY environment variables.
USE_SYSTEM_PROXY = os.getenv("BOTTOM_HUNTER_USE_PROXY") == "1"

# In requests, trust_env=False disables proxy detection from environment.
REQUESTS_TRUST_ENV = USE_SYSTEM_PROXY


def apply_requests_session(session: Any) -> None:
    """Apply project network settings to a requests.Session."""
    session.trust_env = REQUESTS_TRUST_ENV


def apply_urllib() -> None:
    """Install a global urllib opener for urllib.request when proxies are off."""
    if not USE_SYSTEM_PROXY:
        import urllib.request

        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        urllib.request.install_opener(opener)
