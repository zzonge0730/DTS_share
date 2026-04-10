#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


from dts.config import REPO_ROOT, DATA_ROOT
DEFAULT_THRESHOLD_SPEC_PATH = DATA_ROOT / "seam_eval_thresholds_v0_initial_2026-03-31.json"
DEFAULT_PROMOTION_POLICY_PATH = DATA_ROOT / "seam_promotion_policy_v0_initial_2026-03-31.json"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_threshold_spec(path: Path = DEFAULT_THRESHOLD_SPEC_PATH) -> dict[str, Any]:
    return _load_json(path)


def load_promotion_policy(path: Path = DEFAULT_PROMOTION_POLICY_PATH) -> dict[str, Any]:
    return _load_json(path)


def detect_source_commit(repo_root: Path = REPO_ROOT) -> str | None:
    env_commit = os.environ.get("DTS_SOURCE_COMMIT")
    if env_commit:
        return env_commit
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=True,
        )
    except Exception:
        return None
    return proc.stdout.strip() or None


def current_evaluated_at() -> str:
    env_value = os.environ.get("DTS_EVALUATED_AT")
    if env_value:
        return env_value
    return datetime.now().astimezone().isoformat(timespec="seconds")
