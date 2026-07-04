"""
config.py — load settings from a git-ignored .env file (no dependency needed).

Secrets like your Discord webhook URL live in paper-trading/.env, which is
git-ignored so it never gets pushed to GitHub.
"""

import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
_ENV_PATH = os.path.join(_PROJECT_ROOT, ".env")
_loaded = False


def load_env():
    global _loaded
    if _loaded:
        return
    _loaded = True
    if not os.path.exists(_ENV_PATH):
        return
    with open(_ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def get(key, default=None):
    load_env()
    return os.environ.get(key, default)
