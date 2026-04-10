"""캡처(capture) ID / 경로 해석 유틸리티.

battery_case_gui.py와 register_battery_capture_icp.py에서
중복되던 캡처 ID 추출 로직을 하나로 통합한 모듈.
"""
from __future__ import annotations

from pathlib import Path


def capture_id_from_raw_pcd(raw_capture_ply: Path) -> str:
    """원본 PLY 파일명에서 짧은 캡처(capture) ID를 추출한다.

    예시:
        point_cloud_20260317_134008_978.ply -> "978"
        point_cloud_REG_BASE.ply -> "REG_BASE"
        anything_else.ply -> stem
    """
    name = raw_capture_ply.name
    if name.startswith("point_cloud_") and raw_capture_ply.suffix.lower() == ".ply":
        suffix = name[len("point_cloud_"):-len(".ply")]
        tail = suffix.rsplit("_", 1)[-1]
        if tail.isdigit():
            return tail
        return suffix
    return raw_capture_ply.stem


def capture_suffix_from_raw_pcd(raw_pcd_path: Path) -> str | None:
    """원본 PLY 파일명에서 전체 접미사(suffix)를 추출한다.

    예시:
        point_cloud_20260317_134008_978.ply -> "20260317_134008_978"
    """
    name = raw_pcd_path.name
    if not name.startswith("point_cloud_") or raw_pcd_path.suffix.lower() != ".ply":
        return None
    return name[len("point_cloud_"):-len(".ply")]


def guess_rgb_path(raw_pcd_path: Path) -> Path | None:
    """원본 PLY 캡처(capture)에 대응하는 RGB 이미지 경로를 추정한다."""
    name = raw_pcd_path.name
    if not name.startswith("point_cloud_") or raw_pcd_path.suffix.lower() != ".ply":
        return None
    suffix = name[len("point_cloud_"):-len(".ply")]
    candidate = raw_pcd_path.with_name(f"rgb_image_{suffix}.png")
    if candidate.exists():
        return candidate
    return None


def to_windows_unc_path(posix_path: Path) -> str:
    """WSL 경로를 Windows UNC 경로로 변환한다 (PowerShell 연동용).

    /home/user/... -> \\\\wsl$\\Ubuntu\\home\\user\\...
    /mnt/c/...     -> C:\\...
    """
    s = str(posix_path)
    if s.startswith("/mnt/") and len(s) > 5 and s[5] == "/":
        drive = s[5].upper() if len(s) > 5 else s[4].upper()
        return f"{drive}:{s[6:]}".replace("/", "\\")
    # 일반 WSL 경로
    return f"\\\\wsl$\\Ubuntu{s}".replace("/", "\\")
