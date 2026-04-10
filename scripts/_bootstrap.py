"""Ensure the repo root is on sys.path so `import dts` works from any CWD.

Usage (at the top of each script, before any dts imports):
    import _bootstrap  # noqa: F401
"""
import sys
from pathlib import Path

_repo_root = str(Path(__file__).resolve().parent.parent)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

_scripts_dir = str(Path(__file__).resolve().parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)
