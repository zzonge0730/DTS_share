"""DTS 파이프라인 환경 인식 설정 모듈.

설정(Configuration)은 다음 우선순위로 결정됩니다:
1. 함수에 직접 전달된 인자
2. JSON 설정 파일 (저장소 루트의 dts_config.json)
3. DTS_DATA_ROOT 환경 변수
4. 내장 기본값

이 모듈은 기존에 여러 스크립트에 흩어져 있던
모든 경로 상수와 조정 가능한 매개변수를 중앙 집중화합니다.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import numpy as np


# ---------------------------------------------------------------------------
# 저장소 루트 감지
# ---------------------------------------------------------------------------

def _find_repo_root() -> Path:
    """이 파일 기준으로 상위 디렉토리를 탐색해 저장소 루트를 찾습니다.

    CLAUDE.md 또는 .git가 있는 디렉토리를 저장소 루트로 간주합니다.
    """
    current = Path(__file__).resolve().parent
    for _ in range(5):
        if (current / ".git").exists() or (current / "CLAUDE.md").exists():
            return current
        current = current.parent
    return Path(__file__).resolve().parents[1]


REPO_ROOT = _find_repo_root()


# ---------------------------------------------------------------------------
# 설정 파일 로딩 (캐시된 싱글톤)
# ---------------------------------------------------------------------------

_CONFIG_FILE = REPO_ROOT / "dts_config.json"
_cached_config: dict[str, Any] | None = None


def load_config(config_path: Path | None = None) -> dict[str, Any]:
    """JSON 파일에서 DTS 설정을 로드합니다. 파일이 없으면 빈 딕셔너리를 반환합니다."""
    path = config_path or _CONFIG_FILE
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def get_config() -> dict[str, Any]:
    """캐시된 설정을 반환합니다 (프로세스당 한 번 로드)."""
    global _cached_config
    if _cached_config is None:
        _cached_config = load_config()
    return _cached_config


def reset_config() -> None:
    """캐시된 설정을 초기화합니다 (테스트용)."""
    global _cached_config
    _cached_config = None


# ---------------------------------------------------------------------------
# 외부 데이터 루트
# ---------------------------------------------------------------------------

def get_data_root() -> Path | None:
    """설정 파일 또는 환경 변수에서 외부 데이터 루트 경로를 결정합니다.

    설정되지 않은 경우 None을 반환합니다 (파이프라인은 레지스트리의 경로를 그대로 사용).
    """
    cfg = get_config()
    if "data_root" in cfg:
        p = Path(cfg["data_root"])
        return p if p.is_absolute() else REPO_ROOT / p
    env = os.environ.get("DTS_DATA_ROOT")
    if env:
        return Path(env)
    return None


# 레지스트리 경로가 원래 구성된 하드코딩된 기본 경로.
# rebase_path()에서 이 접두사를 제거하고 data_root 아래로 재배치할 때 사용됩니다.
_ORIGINAL_DATA_ROOT = Path("/mnt/c/Users/hanmech/Desktop/DTS_image")


def rebase_path(original: str, data_root: Path | None = None) -> Path:
    """원본 환경의 절대 경로를 현재 data_root 기준 경로로 다시 맞춥니다.

    data_root가 없거나 경로가 기존 개발 환경 접두사로 시작하지 않으면
    경로를 변경 없이 반환합니다.
    """
    p = Path(original)
    if data_root is None:
        return p
    try:
        rel = p.relative_to(_ORIGINAL_DATA_ROOT)
        return data_root / rel
    except ValueError:
        return p


def rebase_registry_paths(registry: dict[str, Any], data_root: Path | None = None) -> dict[str, Any]:
    """레지스트리 딕셔너리 안의 파일 경로를 data_root 기준 경로로 다시 맞춥니다.

    원본 레지스트리 딕셔너리를 직접 수정한 뒤 반환합니다.
    """
    if data_root is None:
        return registry

    path_keys = ("reference_pcd", "raw_capture_ply", "roi_or_eval_pcd",
                 "icp_transform_npy", "icp_report_json")

    if "reference_pcd" in registry:
        registry["reference_pcd"] = str(rebase_path(registry["reference_pcd"], data_root))

    for capture in registry.get("captures", {}).values():
        for key in path_keys:
            if key in capture and isinstance(capture[key], str):
                capture[key] = str(rebase_path(capture[key], data_root))

    return registry


# ---------------------------------------------------------------------------
# 기본 경로 (저장소 기준 상대 경로, 항상 유효)
# ---------------------------------------------------------------------------

DATA_ROOT = REPO_ROOT / "data" / "battery_case"
SCRIPTS_DIR = REPO_ROOT / "scripts"

DEFAULT_CAD_SEAM_DIR = DATA_ROOT / "cad_seams"
DEFAULT_FIXED_REGISTRY = DATA_ROOT / "capture_registry_20260318.json"
DEFAULT_LIVE_REGISTRY = DATA_ROOT / "capture_registry_live.json"
DEFAULT_OUTPUT_ROOT = DATA_ROOT / "live_icp"
DEFAULT_CAMERA_CONFIG = DATA_ROOT / "camera_config.json"
DEFAULT_MECHVIZ_CONFIG = DATA_ROOT / "mechviz_runtime_config.json"
DEFAULT_QUALITY_GATE = DATA_ROOT / "quality_gate_v2_2026-04-08.json"


def get_captures_dir(config: dict[str, Any] | None = None) -> Path:
    """설정(config), dts_config, 환경 변수, 또는 기본값에서 촬영 디렉토리를 반환합니다."""
    if config and "captures_dir" in config and config["captures_dir"]:
        return Path(config["captures_dir"])
    cfg = get_config()
    if "captures_dir" in cfg:
        return Path(cfg["captures_dir"])
    data_root = get_data_root()
    if data_root:
        return data_root / "captures"
    # 레거시 WSL 기본 경로
    return Path("/mnt/c/Users/hanmech/Desktop/DTS_image/captures")


def get_cad_seam_dirs(config: dict[str, Any] | None = None) -> list[Path]:
    """용접선 CSV와 에셋 파일을 찾을 디렉토리 목록을 우선순위대로 반환합니다."""
    if config and "cad_seam_dirs" in config:
        return [Path(d) for d in config["cad_seam_dirs"]]
    cfg = get_config()
    if "cad_seam_dirs" in cfg:
        return [Path(d) for d in cfg["cad_seam_dirs"]]
    dirs = [DEFAULT_CAD_SEAM_DIR]
    # 외부 CAD 용접선 디렉토리 확인
    data_root = get_data_root()
    if data_root:
        ext_cad = data_root / "cad"
        if ext_cad.exists():
            dirs.append(ext_cad)
    else:
        # 레거시 WSL 경로
        legacy = Path("/mnt/c/Users/hanmech/Desktop/DTS_image/cad")
        if legacy.exists():
            dirs.append(legacy)
    return dirs


def get_roi_bounds(config: dict[str, Any] | None = None) -> tuple[np.ndarray, np.ndarray]:
    """설정 또는 기본값에서 관심영역(ROI) 범위 (roi_min, roi_max) 배열을 반환합니다."""
    if config:
        if "roi_min" in config:
            roi_min = np.array(config["roi_min"], dtype=float)
        else:
            roi_min = DEFAULT_ROI_MIN
        if "roi_max" in config:
            roi_max = np.array(config["roi_max"], dtype=float)
        else:
            roi_max = DEFAULT_ROI_MAX
        return roi_min, roi_max
    return DEFAULT_ROI_MIN.copy(), DEFAULT_ROI_MAX.copy()


# ---------------------------------------------------------------------------
# 정합(ICP) 매개변수
# ---------------------------------------------------------------------------

DEFAULT_ROI_MIN = np.array([-450.0, -350.0, 1150.0], dtype=float)
DEFAULT_ROI_MAX = np.array([450.0, 250.0, 1450.0], dtype=float)

DEFAULT_ICP_STAGES: list[dict[str, Any]] = [
    {"voxel_mm": 8.0, "max_corr_mm": 24.0, "max_iter": 50, "method": "point_to_plane"},
    {"voxel_mm": 4.0, "max_corr_mm": 12.0, "max_iter": 60, "method": "point_to_plane"},
    {"voxel_mm": 2.0, "max_corr_mm": 6.0,  "max_iter": 60, "method": "point_to_plane"},
    {"voxel_mm": 1.0, "max_corr_mm": 3.0,  "max_iter": 80, "method": "point_to_plane"},
]

DEFAULT_SEAM_LOCAL_REFINEMENT_STAGES: list[dict[str, Any]] = [
    {"voxel_mm": 2.0, "max_corr_mm": 4.0, "max_iter": 50, "method": "point_to_plane"},
    {"voxel_mm": 1.0, "max_corr_mm": 2.0, "max_iter": 70, "method": "point_to_plane"},
]
