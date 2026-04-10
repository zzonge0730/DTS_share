#!/usr/bin/env python3
"""
battery_case_gui.py - Battery-case demo GUI for pipeline execution.

This is a small operator/demo UI, not a production control panel.

Features:
- select capture ID from the fixed battery-case registry
- select one or more seam candidates
- run the current battery seam pipeline
- save pose/1100 outputs under data/battery_case/gui_runs/
- generate RGB overlay preview for the selected capture

Runtime note:
- best run from a host Python with tkinter available
- current WSL dev environment may not include tkinter
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import queue
import re
import subprocess
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import open3d as o3d
from PIL import Image


def _ensure_fontconfig_for_windows_fonts() -> None:
    windows_fonts_dir = Path("/mnt/c/Windows/Fonts")
    if not windows_fonts_dir.exists():
        return

    config_path = Path("/tmp/dts-wsl-fonts.conf")
    config_text = """<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
  <dir>/usr/share/fonts</dir>
  <dir>/usr/local/share/fonts</dir>
  <dir>/mnt/c/Windows/Fonts</dir>
</fontconfig>
"""
    try:
        if not config_path.exists() or config_path.read_text(encoding="utf-8") != config_text:
            config_path.write_text(config_text, encoding="utf-8")
        os.environ.setdefault("FONTCONFIG_FILE", str(config_path))
    except OSError:
        return


_ensure_fontconfig_for_windows_fonts()

try:
    import tkinter as tk
    from tkinter import font as tkfont
    from tkinter import messagebox, ttk
    from PIL import ImageTk
except ImportError:
    tk = None
    ttk = None
    tkfont = None
    messagebox = None
    ImageTk = None


import _bootstrap  # noqa: F401 — repo root + scripts/ on sys.path
from dts.config import REPO_ROOT, SCRIPTS_DIR

from battery_seam_pipeline import SEAM_CANDIDATES, process_seam
from mecheye_capture import (
    DEFAULT_CAMERA_CONFIG,
    capture_bundle,
    discover_cameras,
    load_camera_config,
    save_camera_config,
    sdk_status_text,
)
from dts.config import get_captures_dir
from mechviz_runtime import (
    DEFAULT_MECHVIZ_CONFIG,
    load_mechviz_runtime_config,
    open_mechviz_project,
    probe_windows_pid,
    start_outer_move_service,
    stop_outer_move_service,
    trigger_mechviz_execution,
)
from overlay_seam_on_rgb import (
    DEFAULT_COLORS,
    draw_polyline,
    load_pose_csv,
    seam_points_to_pixels,
)
from register_battery_capture_icp import (
    DEFAULT_LIVE_REGISTRY,
    load_live_registry,
    register_live_capture_icp,
)


DEFAULT_REGISTRY = REPO_ROOT / "data" / "battery_case" / "capture_registry_20260318.json"
GUI_RUNS_DIR = REPO_ROOT / "data" / "battery_case" / "gui_runs"


def load_capture_registry(path: Path = DEFAULT_REGISTRY) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def resolve_canonical_eval_pcd(capture_entry: dict[str, Any]) -> Path:
    canonical = capture_entry.get("canonical_nn_evaluation_cloud")
    if canonical == "raw_capture_ply":
        return Path(capture_entry["raw_capture_ply"])
    roi = capture_entry.get("roi_or_eval_pcd")
    if roi:
        return Path(roi)
    raise ValueError("capture entry has no canonical evaluation cloud")


from dts.paths import (
    guess_rgb_path,
    capture_suffix_from_raw_pcd,
    capture_id_from_raw_pcd as live_capture_id_from_raw_pcd,
)


def capture_display_label(capture_id: str, entry: dict[str, Any]) -> str:
    """Build a human-readable label for a capture entry."""
    explicit = entry.get("label")
    if explicit:
        return str(explicit)

    has_icp = bool(entry.get("icp_transform_npy"))
    suffix = capture_suffix_from_raw_pcd(Path(entry.get("raw_capture_ply", "")))

    if suffix and "_" in suffix:
        # e.g. "20260319_120000_gui" → "2026-03-19 12:00 gui"
        parts = suffix.split("_")
        date_part = parts[0] if len(parts[0]) == 8 else None
        time_part = parts[1] if len(parts) > 1 and len(parts[1]) == 6 else None
        tag = parts[2] if len(parts) > 2 else None

        date_str = ""
        if date_part and date_part.isdigit():
            date_str = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]}"
        time_str = ""
        if time_part and time_part.isdigit():
            time_str = f"{time_part[:2]}:{time_part[2:4]}"

        label_parts = [capture_id]
        if date_str:
            label_parts.append(f"촬영 {date_str} {time_str}".strip())
        if tag:
            label_parts.append(tag)
        if not has_icp:
            label_parts.append("(pending ICP)")
        return " · ".join(label_parts)

    if not has_icp:
        return f"{capture_id} · (pending ICP)"
    return capture_id


def build_live_capture_entry(raw_pcd_path: Path) -> dict[str, Any]:
    suffix = capture_suffix_from_raw_pcd(raw_pcd_path)
    if suffix is None:
        raise ValueError(f"unsupported capture name: {raw_pcd_path.name}")

    depth_path = raw_pcd_path.with_name(f"depth_image_{suffix}.tiff")
    meta_path = raw_pcd_path.with_name(f"capture_meta_{suffix}.json")
    notes = [
        "captures/ 폴더에서 감지된 실시간 촬영본",
        "아직 ICP 변환이 등록되지 않아 검토만 가능하고 실행은 불가",
    ]
    if depth_path.exists():
        notes.append(f"Depth: {depth_path}")
    if meta_path.exists():
        notes.append(f"메타 정보: {meta_path}")

    return {
        "raw_capture_ply": str(raw_pcd_path),
        "roi_or_eval_pcd": None,
        "icp_transform_npy": None,
        "canonical_nn_evaluation_cloud": "raw_capture_ply",
        "notes": notes,
        "_source": "live_capture_scan",
    }


def merge_capture_entries(
    registry: dict[str, Any], captures_dir: Path | None
) -> tuple[list[str], dict[str, dict[str, Any]]]:
    captures = {k: dict(v) for k, v in registry["captures"].items()}
    ids = sorted(captures.keys())
    if captures_dir is None or not captures_dir.exists():
        return ids, captures

    known_raw_paths = {str(Path(v["raw_capture_ply"])) for v in captures.values()}
    live_candidates: list[tuple[float, str, dict[str, Any]]] = []
    for raw_pcd in captures_dir.rglob("point_cloud_*.ply"):
        raw_pcd = raw_pcd.resolve()
        if str(raw_pcd) in known_raw_paths:
            continue

        capture_id = live_capture_id_from_raw_pcd(raw_pcd)
        if not capture_id:
            continue
        if capture_id in captures:
            capture_id = f"live:{capture_id}"

        live_candidates.append((raw_pcd.stat().st_mtime, capture_id, build_live_capture_entry(raw_pcd)))

    live_candidates.sort(key=lambda item: item[0])
    for _mtime, capture_id, entry in live_candidates:
        captures[capture_id] = entry
        ids.append(capture_id)

    return ids, captures


def generate_overlay_image(
    rgb_path: Path,
    raw_pcd_path: Path,
    pose_csv_paths: list[Path],
    out_path: Path,
) -> tuple[Path, dict[str, dict[str, float]]]:
    rgb = Image.open(rgb_path).convert("RGB")
    width, height = rgb.size

    raw_pcd = o3d.io.read_point_cloud(str(raw_pcd_path))
    raw_pts = np.asarray(raw_pcd.points)
    if len(raw_pts) != width * height:
        raise ValueError(
            f"raw point count {len(raw_pts)} does not match image size {width}x{height}"
        )

    overlay = rgb.copy()
    stats: dict[str, dict[str, float]] = {}

    for i, pose_csv in enumerate(pose_csv_paths):
        seam_pts = load_pose_csv(pose_csv)
        pixels, seam_stats = seam_points_to_pixels(seam_pts, raw_pcd, width, height)
        color = DEFAULT_COLORS[i % len(DEFAULT_COLORS)]
        draw_polyline(overlay, pixels, color, pose_csv.stem.replace("_pose", ""))
        stats[pose_csv.stem] = seam_stats

    out_path.parent.mkdir(parents=True, exist_ok=True)
    overlay.save(out_path)
    return out_path, stats


def summarize_run_summary(summary: dict[str, Any]) -> dict[str, float]:
    results = summary.get("results", [])
    if not results:
        return {
            "avg_mean_nn_mm": float("inf"),
            "avg_p90_nn_mm": float("inf"),
            "worst_max_nn_mm": float("inf"),
            "avg_centerline_p90_mm": float("inf"),
            "avg_tangent_p90_deg": float("inf"),
            "avg_corridor_inlier_ratio": 0.0,
            "corridor_pass": False,
            "total_poses": 0.0,
        }

    mean_vals = [float(item["score"]["mean_nn_mm"]) for item in results]
    p90_vals = [float(item["score"]["p90_nn_mm"]) for item in results]
    max_vals = [float(item["score"]["max_nn_mm"]) for item in results]
    poses = [int(item["n_poses"]) for item in results]
    out = {
        "avg_mean_nn_mm": float(np.mean(mean_vals)),
        "avg_p90_nn_mm": float(np.mean(p90_vals)),
        "worst_max_nn_mm": float(np.max(max_vals)),
        "total_poses": float(np.sum(poses)),
    }
    if all("centerline_p90_mm" in item["score"] for item in results):
        centerline_p90_vals = [float(item["score"]["centerline_p90_mm"]) for item in results]
        out["avg_centerline_p90_mm"] = float(np.mean(centerline_p90_vals))
    else:
        out["avg_centerline_p90_mm"] = float("inf")
    if all("tangent_p90_deg" in item["score"] for item in results):
        tangent_p90_vals = [float(item["score"]["tangent_p90_deg"]) for item in results]
        out["avg_tangent_p90_deg"] = float(np.mean(tangent_p90_vals))
    else:
        out["avg_tangent_p90_deg"] = float("inf")
    if all("corridor_inlier_ratio" in item["score"] for item in results):
        corridor_ratio_vals = [float(item["score"]["corridor_inlier_ratio"]) for item in results]
        out["avg_corridor_inlier_ratio"] = float(np.mean(corridor_ratio_vals))
    else:
        out["avg_corridor_inlier_ratio"] = 0.0
    if all("corridor_pass" in item["score"] for item in results):
        out["corridor_pass"] = bool(all(bool(item["score"]["corridor_pass"]) for item in results))
    else:
        out["corridor_pass"] = False
    return out


def _format_geometry_summary(metrics: dict[str, float]) -> str:
    centerline_p90 = metrics.get("avg_centerline_p90_mm", float("inf"))
    tangent_p90 = metrics.get("avg_tangent_p90_deg", float("inf"))
    corridor_ratio = metrics.get("avg_corridor_inlier_ratio", 0.0)
    corridor_pass = metrics.get("corridor_pass", False)
    if not np.isfinite(centerline_p90) or not np.isfinite(tangent_p90):
        return ""
    return (
        f"centerline P90 {centerline_p90:.3f}mm · "
        f"tangent P90 {tangent_p90:.2f}deg · "
        f"corridor {corridor_ratio:.1%} · "
        f"{'PASS' if corridor_pass else 'CHECK'}"
    )


def recommended_variant_name(
    baseline_summary: dict[str, Any],
    corrected_summary: dict[str, Any],
) -> str:
    baseline = summarize_run_summary(baseline_summary)
    corrected = summarize_run_summary(corrected_summary)
    if corrected["avg_mean_nn_mm"] < baseline["avg_mean_nn_mm"] - 1e-9:
        return "corrected"
    if abs(corrected["avg_mean_nn_mm"] - baseline["avg_mean_nn_mm"]) <= 1e-9:
        if corrected["worst_max_nn_mm"] <= baseline["worst_max_nn_mm"] + 1e-9:
            return "corrected"
    return "baseline"


def _summary_label(summary: dict[str, Any] | None, fallback: str) -> str:
    if not summary:
        return fallback
    return str(summary.get("compare_label") or summary.get("variant_label") or fallback)


def build_comparison_display(
    baseline_summary: dict[str, Any] | None,
    corrected_summary: dict[str, Any] | None,
    current_summary: dict[str, Any] | None,
) -> dict[str, str]:
    if baseline_summary is not None and corrected_summary is not None:
        baseline = summarize_run_summary(baseline_summary)
        corrected = summarize_run_summary(corrected_summary)
        baseline_label = _summary_label(baseline_summary, "원본")
        corrected_label = _summary_label(corrected_summary, "보정안")
        recommended = recommended_variant_name(baseline_summary, corrected_summary)
        delta_mean = corrected["avg_mean_nn_mm"] - baseline["avg_mean_nn_mm"]
        delta_p90 = corrected["avg_p90_nn_mm"] - baseline["avg_p90_nn_mm"]
        delta_max = corrected["worst_max_nn_mm"] - baseline["worst_max_nn_mm"]

        small_gap = (
            abs(delta_mean) < 0.10
            and abs(delta_p90) < 0.15
            and abs(delta_max) < 0.25
        )
        if small_gap:
            headline = "비교 결과 · 실질 차이 미미"
        elif recommended == "corrected":
            headline = f"비교 결과 · {corrected_label} 권장"
        else:
            headline = f"비교 결과 · {baseline_label} 유지 권장"

        return {
            "headline": headline,
            "detail": (
                f"평균 NN Δ {delta_mean:+.3f}mm · "
                f"P90 Δ {delta_p90:+.3f}mm · "
                f"최대 Δ {delta_max:+.3f}mm"
            ),
            "left": (
                f"{baseline_label}  mean {baseline['avg_mean_nn_mm']:.3f} · "
                f"p90 {baseline['avg_p90_nn_mm']:.3f} · "
                f"max {baseline['worst_max_nn_mm']:.3f}"
                + (
                    f"\n{_format_geometry_summary(baseline)}"
                    if _format_geometry_summary(baseline)
                    else ""
                )
            ),
            "right": (
                f"{corrected_label}  mean {corrected['avg_mean_nn_mm']:.3f} · "
                f"p90 {corrected['avg_p90_nn_mm']:.3f} · "
                f"max {corrected['worst_max_nn_mm']:.3f}"
                + (
                    f"\n{_format_geometry_summary(corrected)}"
                    if _format_geometry_summary(corrected)
                    else ""
                )
            ),
        }

    if current_summary is not None:
        metrics = summarize_run_summary(current_summary)
        variant = _summary_label(
            current_summary,
            "보정안" if current_summary.get("variant") == "corrected" else "원본",
        )
        geom_text = _format_geometry_summary(metrics)
        return {
            "headline": f"현재 결과 · {variant}",
            "detail": (
                f"평균 NN {metrics['avg_mean_nn_mm']:.3f}mm · "
                f"P90 {metrics['avg_p90_nn_mm']:.3f}mm · "
                f"최대 {metrics['worst_max_nn_mm']:.3f}mm"
                + (f"\n{geom_text}" if geom_text else "")
            ),
            "left": f"총 포즈 수 {int(metrics['total_poses'])}",
            "right": "보정 비교를 실행하면 원본/보정안을 나란히 비교합니다",
        }

    return {
        "headline": "비교 결과 대기 중",
        "detail": "경로 생성 또는 보정 비교를 실행하면 여기에 판단 요약이 표시됩니다",
        "left": "원본/보정안 수치 비교 없음",
        "right": "오버레이 비교는 아래 패널에서 확인합니다",
    }


def derive_viz_output_paths(pose_csv: Path) -> dict[str, Path]:
    stem = pose_csv.stem
    if stem.endswith("_pose"):
        base = stem[:-len("_pose")]
    else:
        base = stem
    return {
        "viz_csv": pose_csv.with_name(f"{base}_viz.csv"),
    }


def result_record_from_tree_item(tree_item: dict[str, Any], seam_name: str) -> dict[str, Any]:
    values = list(tree_item.get("values", []))
    return {
        "name": str(values[0]) if values else seam_name,
        "n_poses": int(values[1]),
        "mean_nn_mm": float(values[2]),
        "p90_nn_mm": float(values[3]),
        "max_nn_mm": float(values[4]),
        "pose_csv": str(values[5]),
        "txt_1100": str(values[6]),
    }


def resolve_result_open_target(
    column_id: str,
    record: dict[str, Any],
    current_summary: dict[str, Any] | None,
) -> Path:
    if column_id == "#6":
        return Path(record["pose_csv"])
    if column_id == "#7":
        return Path(record["txt_1100"])
    if current_summary and current_summary.get("run_dir"):
        return Path(str(current_summary["run_dir"]))
    return Path(record["pose_csv"]).parent


def parse_dts_e2e_output(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "verdict": None,
        "gap_mode": None,
        "ok_log_grew": None,
        "ng_log_grew": None,
        "log_dir": None,
        "sections": {},
    }
    patterns = {
        "verdict": r"verdict:\s*(PASS|FAIL)",
        "gap_mode": r"gap mode:\s*([a-zA-Z0-9_]+)",
        "ok_log_grew": r"ok log grew:\s*(True|False)",
        "ng_log_grew": r"ng log grew:\s*(True|False)",
        "log_dir": r"log dir:\s*(.+)",
    }
    for key, pattern in patterns.items():
        m = re.search(pattern, text)
        if not m:
            continue
        value = m.group(1).strip()
        if key in ("ok_log_grew", "ng_log_grew"):
            result[key] = value == "True"
        else:
            result[key] = value

    # Extract structured log sections: [robot.out], [vision.out], [ok.log tail], etc.
    section_pattern = re.compile(r"^\[([^\]]+)\]\s*$", re.MULTILINE)
    matches = list(section_pattern.finditer(text))
    for i, m in enumerate(matches):
        section_name = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            result["sections"][section_name] = body

    return result


def describe_capture_entry(
    capture_id: str,
    capture_entry: dict[str, Any],
    fixed_registry: dict[str, Any],
) -> dict[str, Any]:
    is_fixed = capture_id in fixed_registry.get("captures", {})
    has_icp = bool(capture_entry.get("icp_transform_npy"))
    source = str(capture_entry.get("_source") or ("fixed_registry" if is_fixed else "live_capture_scan"))

    if is_fixed:
        return {
            "origin": source,
            "status": "fixed_ready",
            "status_label": "고정 기준 캡처",
            "allow_icp_register": False,
            "icp_register_reason": "고정 기준 캡처는 GUI에서 다시 ICP 등록하지 않습니다.",
        }

    if has_icp:
        return {
            "origin": source,
            "status": "live_ready",
            "status_label": "실행 가능",
            "allow_icp_register": False,
            "icp_register_reason": "이미 ICP가 등록된 캡처입니다.",
        }

    return {
        "origin": source,
        "status": "pending_icp",
        "status_label": "pending ICP",
        "allow_icp_register": True,
        "icp_register_reason": "",
    }


def finalize_dts_e2e_verdict(parsed: dict[str, Any], returncode: int) -> dict[str, str]:
    raw_verdict = str(parsed.get("verdict") or "UNKNOWN").upper()
    if returncode != 0:
        return {
            "verdict": "FAIL",
            "reason": f"exit_code={returncode}",
        }
    if raw_verdict in {"PASS", "FAIL"}:
        return {
            "verdict": raw_verdict,
            "reason": "summary",
        }
    return {
        "verdict": "UNKNOWN",
        "reason": "summary_missing",
    }


class QueueWriter(io.TextIOBase):
    def __init__(self, out_queue: "queue.Queue[tuple[str, Any]]"):
        self.out_queue = out_queue

    def write(self, s: str) -> int:
        if s:
            self.out_queue.put(("log", s))
        return len(s)

    def flush(self) -> None:
        return None


class BatteryCaseGuiApp:
    def __init__(self, root: "tk.Tk"):
        self.root = root
        self.root.title("DTS Battery Case Demo")
        self._show_root_window()

        self.registry = load_capture_registry()
        self.live_registry = load_live_registry(
            DEFAULT_LIVE_REGISTRY,
            reference_pcd=self.registry.get("reference_pcd"),
        )
        self.camera_config = load_camera_config()
        self.mechviz_config = load_mechviz_runtime_config(DEFAULT_MECHVIZ_CONFIG)
        self.capture_ids, self.capture_entries = merge_capture_entries(
            self._combined_registry(),
            Path(self.camera_config.get("captures_dir") or get_captures_dir()),
        )
        self._rebuild_capture_labels()
        self.ui_queue: "queue.Queue[tuple[str, Any]]" = queue.Queue()
        self.overlay_left_photo = None
        self.overlay_right_photo = None
        self.overlay_left_path: Path | None = None
        self.overlay_right_path: Path | None = None
        self._overlay_zoom: dict[str, float] = {"left": 1.0, "right": 1.0}
        self._overlay_pan: dict[str, tuple[int, int]] = {"left": (0, 0), "right": (0, 0)}
        self._overlay_drag_start: dict[str, tuple[int, int] | None] = {"left": None, "right": None}
        self._overlay_pil: dict[str, Image.Image | None] = {"left": None, "right": None}
        self._overlay_item: dict[str, int | None] = {"left": None, "right": None}
        self._overlay_text_item: dict[str, int | None] = {"left": None, "right": None}
        self._overlay_zoom_after: dict[str, str | None] = {"left": None, "right": None}
        self.run_thread: threading.Thread | None = None
        self.camera_thread: threading.Thread | None = None
        self.icp_thread: threading.Thread | None = None
        self.correction_thread: threading.Thread | None = None
        self.export_thread: threading.Thread | None = None
        self.e2e_thread: threading.Thread | None = None
        self.mechviz_service_thread: threading.Thread | None = None
        self.mechviz_open_thread: threading.Thread | None = None
        self.mechviz_simulate_thread: threading.Thread | None = None
        self.baseline_summary: dict[str, Any] | None = None
        self.corrected_summary: dict[str, Any] | None = None
        self.current_summary: dict[str, Any] | None = None
        self.mechviz_service_pid: int | None = None

        default_label = self.capture_id_to_label.get(self.capture_ids[-1], "") if self.capture_ids else ""
        self.capture_var = tk.StringVar(value=default_label)
        self.camera_ip_var = tk.StringVar(value=self.camera_config.get("camera_ip", ""))
        self.captures_dir_var = tk.StringVar(
            value=str(self.camera_config.get("captures_dir") or get_captures_dir())
        )
        self.camera_status_var = tk.StringVar(value=sdk_status_text())
        self.step_var = tk.StringVar(value="5.0")
        self.edge_snap_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="대기")
        self.progress_badge_var = tk.StringVar(value="대기 중")
        self.output_dir_var = tk.StringVar(value="-")
        self.review_var = tk.StringVar(value="검토안 미선택")
        self.mechviz_service_var = tk.StringVar(value="서비스 중지")
        self.preview_left_title_var = tk.StringVar(value="현재 결과")
        self.preview_right_title_var = tk.StringVar(value="비교 없음")
        self.compare_headline_var = tk.StringVar(value="비교 결과 대기 중")
        self.compare_detail_var = tk.StringVar(value="경로 생성 또는 보정 비교를 실행하면 여기에 판단 요약이 표시됩니다")
        self.compare_left_var = tk.StringVar(value="원본/보정안 수치 비교 없음")
        self.compare_right_var = tk.StringVar(value="오버레이 비교는 아래 패널에서 확인합니다")

        self._configure_style()
        self._build_ui()
        self._refresh_capture_notes()
        self._refresh_action_state()
        self._reset_overlay_compare(
            left_text="아직 생성된 오버레이가 없습니다",
            right_text="보정 비교를 실행하면 원본/보정안을 나란히 표시합니다",
        )
        self.root.after(100, self._poll_queue)

    def _show_root_window(self) -> None:
        """초기 창을 화면 안쪽 중앙에 보이도록 배치합니다."""
        width = 1440
        height = 920
        try:
            self.root.update_idletasks()
            screen_w = max(int(self.root.winfo_screenwidth()), 1)
            screen_h = max(int(self.root.winfo_screenheight()), 1)
            width = min(width, max(screen_w - 80, 640))
            height = min(height, max(screen_h - 80, 480))
            x = max((screen_w - width) // 2, 0)
            y = max((screen_h - height) // 2, 0)
            self.root.geometry(f"{width}x{height}+{x}+{y}")
            self.root.deiconify()
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.root.after(250, lambda: self.root.attributes("-topmost", False))
            self.root.after(300, self.root.focus_force)
        except tk.TclError:
            # 창 표시 환경이 제한된 경우에는 기본 geometry만 적용합니다.
            self.root.geometry(f"{width}x{height}")

    def _iter_action_buttons(self, parent: tk.Misc | None = None):
        parent = self.root if parent is None else parent
        for child in parent.winfo_children():
            if isinstance(child, ttk.Button):
                yield child
            yield from self._iter_action_buttons(child)

    def _worker_threads(self) -> list[tuple[str, threading.Thread | None]]:
        return [
            ("카메라", self.camera_thread),
            ("ICP 등록", self.icp_thread),
            ("경로 생성", self.run_thread),
            ("보정 비교", self.correction_thread),
            ("Mech-Viz 내보내기", self.export_thread),
            ("DTS 자동 검증", self.e2e_thread),
            ("Mech-Viz 서비스", self.mechviz_service_thread),
            ("Mech-Viz 프로젝트 열기", self.mechviz_open_thread),
            ("Mech-Viz 시뮬레이션", self.mechviz_simulate_thread),
        ]

    def _active_task_name(self) -> str | None:
        for task_name, thread in self._worker_threads():
            if thread is not None and thread.is_alive():
                return task_name
        return None

    def _ensure_idle(self) -> bool:
        active_task = self._active_task_name()
        if active_task is None:
            return True
        self._show_error(f"현재 {active_task} 작업이 실행 중입니다. 완료 후 다시 시도해 주세요.")
        return False

    def _sync_mechviz_service_state(self) -> None:
        pid = self.mechviz_service_pid
        if pid is None:
            return
        probe = probe_windows_pid(pid)
        if probe.get("alive") is False:
            # Only clear PID when we got a definitive "not alive" answer.
            # If alive is None (timeout / interop error), keep the PID.
            self.mechviz_service_pid = None
            self.mechviz_service_var.set("서비스 중지")
            if not (self.mechviz_service_thread and self.mechviz_service_thread.is_alive()):
                self.status_var.set("Mech-Viz 서비스 중지")
        elif probe.get("alive") is None:
            # Probe failed (timeout or interop error) — keep PID, log warning
            self.log_text.insert(
                "end",
                f"⚠ 서비스 PID {pid} 상태 확인 실패 (기존 PID 유지): "
                f"{probe.get('interop_error', 'unknown')}\n",
            )
            self.log_text.see("end")

    def _refresh_action_state(self) -> None:
        active_task = self._active_task_name()
        is_busy = active_task is not None
        self.progress_badge_var.set(f"진행 중 · {active_task}" if is_busy else "대기 중")
        self.progress_badge_label.configure(style="BusyBadge.TLabel" if is_busy else "IdleBadge.TLabel")

        for button in self._iter_action_buttons():
            button.state(["disabled"] if is_busy else ["!disabled"])

        if is_busy or not self._selected_capture_id():
            self.icp_register_button.state(["disabled"])
            return

        entry = self.capture_entries.get(self._selected_capture_id())
        if entry is None:
            self.icp_register_button.state(["disabled"])
            return

        capture_info = describe_capture_entry(self._selected_capture_id(), entry, self.registry)
        self.icp_register_button.state(["!disabled"] if capture_info["allow_icp_register"] else ["disabled"])

    def _open_path_in_host(self, target: Path) -> None:
        windows_target = self._to_windows_unc_path(target)
        escaped = windows_target.replace("'", "''")
        proc = subprocess.run(
            [
                "powershell.exe",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                f"Start-Process -FilePath '{escaped}'",
            ],
            capture_output=True,
        )
        stdout = proc.stdout.decode("utf-8", errors="replace") if proc.stdout else ""
        stderr = proc.stderr.decode("utf-8", errors="replace") if proc.stderr else ""
        combined = stdout + ("\n" + stderr if stderr else "")
        if proc.returncode != 0:
            raise RuntimeError(f"경로를 열지 못했습니다: {combined}")

    def _build_preview_title(self, summary: dict[str, Any] | None, fallback: str) -> str:
        if not summary:
            return fallback
        metrics = summarize_run_summary(summary)
        if np.isfinite(metrics["avg_mean_nn_mm"]):
            return f"{fallback} · mean {metrics['avg_mean_nn_mm']:.3f} · max {metrics['worst_max_nn_mm']:.3f}"
        return fallback

    def _build_overlay_placeholder(self, label: str, summary: dict[str, Any] | None) -> str:
        if summary and summary.get("overlay_warning"):
            return f"{label}\n오버레이 생성 실패\n{summary['overlay_warning']}"
        return f"{label}\n생성된 오버레이가 없습니다"

    def _set_overlay_panel(
        self,
        *,
        side: str,
        title: str,
        summary: dict[str, Any] | None,
        empty_text: str,
    ) -> None:
        title_var = self.preview_left_title_var if side == "left" else self.preview_right_title_var
        frame = self.overlay_left_frame if side == "left" else self.overlay_right_frame
        canvas = self.overlay_left_canvas if side == "left" else self.overlay_right_canvas
        title_var.set(title)
        frame.configure(text=title)

        overlay_path = Path(summary["overlay_path"]) if summary and summary.get("overlay_path") else None
        if overlay_path and overlay_path.exists() and ImageTk is not None:
            pil_image = Image.open(overlay_path).convert("RGB")
            self._overlay_pil[side] = pil_image
            self._overlay_zoom[side] = 1.0
            self._overlay_pan[side] = (0, 0)
            self.overlay_left_path if side == "left" else None  # noqa — just for path storage below
        else:
            pil_image = None
            self._overlay_pil[side] = None
            self._overlay_zoom[side] = 1.0
            self._overlay_pan[side] = (0, 0)

        if side == "left":
            self.overlay_left_path = overlay_path
        else:
            self.overlay_right_path = overlay_path

        # Delay render so canvas has its layout size.
        canvas.after(50, lambda: self._redraw_overlay_canvas(side, empty_text))

    def _bind_overlay_canvas(self, canvas: tk.Canvas, side: str) -> None:
        canvas.bind("<MouseWheel>", lambda e: self._on_overlay_scroll(side, e))
        canvas.bind("<Button-4>", lambda e: self._on_overlay_scroll(side, e))
        canvas.bind("<Button-5>", lambda e: self._on_overlay_scroll(side, e))
        canvas.bind("<ButtonPress-1>", lambda e: self._on_overlay_drag_start(side, e))
        canvas.bind("<B1-Motion>", lambda e: self._on_overlay_drag(side, e))
        canvas.bind("<ButtonRelease-1>", lambda e: self._on_overlay_drag_end(side, e))
        canvas.bind("<Double-1>", lambda e: self._on_overlay_reset_zoom(side))

    def _redraw_overlay_canvas(self, side: str, empty_text: str = "") -> None:
        canvas = self.overlay_left_canvas if side == "left" else self.overlay_right_canvas
        pil_image = self._overlay_pil[side]

        # Clear old items
        old_img = self._overlay_item[side]
        old_txt = self._overlay_text_item[side]
        if old_img is not None:
            canvas.delete(old_img)
            self._overlay_item[side] = None
        if old_txt is not None:
            canvas.delete(old_txt)
            self._overlay_text_item[side] = None

        if pil_image is None:
            canvas.update_idletasks()
            cw = canvas.winfo_width()
            ch = canvas.winfo_height()
            tid = canvas.create_text(cw // 2, ch // 2, text=empty_text, fill="#888888",
                                     font=("TkDefaultFont", 10), justify="center")
            self._overlay_text_item[side] = tid
            if side == "left":
                self.overlay_left_photo = None
            else:
                self.overlay_right_photo = None
            return

        self._render_overlay_image(side)

    def _render_overlay_image(self, side: str) -> None:
        """Render the overlay image at current zoom level."""
        canvas = self.overlay_left_canvas if side == "left" else self.overlay_right_canvas
        pil_image = self._overlay_pil[side]
        if pil_image is None:
            return

        canvas.update_idletasks()
        cw = max(canvas.winfo_width(), 200)
        ch = max(canvas.winfo_height(), 150)
        zoom = self._overlay_zoom[side]

        img_w, img_h = pil_image.size
        base_scale = min(cw / img_w, ch / img_h)
        scale = base_scale * zoom
        display_w = max(int(img_w * scale), 1)
        display_h = max(int(img_h * scale), 1)
        pan_x, pan_y = self._overlay_pan[side]

        resized = pil_image.resize((display_w, display_h), Image.LANCZOS)
        photo = ImageTk.PhotoImage(resized)

        # Remove old image item, create new one at center
        old_img = self._overlay_item[side]
        if old_img is not None:
            canvas.delete(old_img)
        iid = canvas.create_image(cw // 2 + pan_x, ch // 2 + pan_y, anchor="center", image=photo)
        self._overlay_item[side] = iid

        if side == "left":
            self.overlay_left_photo = photo
        else:
            self.overlay_right_photo = photo

    def _on_overlay_scroll(self, side: str, event: Any) -> None:
        if self._overlay_pil[side] is None:
            return
        if event.num == 4 or (hasattr(event, "delta") and event.delta > 0):
            factor = 1.2
        else:
            factor = 1 / 1.2
        new_zoom = max(0.5, min(self._overlay_zoom[side] * factor, 10.0))
        self._overlay_zoom[side] = new_zoom

        # Debounce: only re-render after scroll stops for 80ms
        pending = self._overlay_zoom_after[side]
        if pending is not None:
            self.root.after_cancel(pending)
        self._overlay_zoom_after[side] = self.root.after(
            80, lambda: self._finish_zoom(side)
        )

    def _finish_zoom(self, side: str) -> None:
        self._overlay_zoom_after[side] = None
        self._render_overlay_image(side)

    def _on_overlay_drag_start(self, side: str, event: Any) -> None:
        self._overlay_drag_start[side] = (event.x, event.y)

    def _on_overlay_drag(self, side: str, event: Any) -> None:
        start = self._overlay_drag_start[side]
        if start is None or self._overlay_item[side] is None:
            return
        dx = event.x - start[0]
        dy = event.y - start[1]
        canvas = self.overlay_left_canvas if side == "left" else self.overlay_right_canvas
        canvas.move(self._overlay_item[side], dx, dy)
        pan_x, pan_y = self._overlay_pan[side]
        self._overlay_pan[side] = (pan_x + dx, pan_y + dy)
        self._overlay_drag_start[side] = (event.x, event.y)

    def _on_overlay_drag_end(self, side: str, _event: Any) -> None:
        self._overlay_drag_start[side] = None

    def _on_overlay_reset_zoom(self, side: str) -> None:
        self._overlay_zoom[side] = 1.0
        self._overlay_pan[side] = (0, 0)
        self._render_overlay_image(side)

    def _reset_overlay_compare(self, left_text: str, right_text: str) -> None:
        compare_display = build_comparison_display(None, None, None)
        self.compare_headline_var.set(compare_display["headline"])
        self.compare_detail_var.set(compare_display["detail"])
        self.compare_left_var.set(compare_display["left"])
        self.compare_right_var.set(compare_display["right"])
        self._set_overlay_panel(side="left", title="현재 결과", summary=None, empty_text=left_text)
        self._set_overlay_panel(side="right", title="비교 없음", summary=None, empty_text=right_text)

    def _refresh_overlay_compare(self) -> None:
        compare_display = build_comparison_display(
            self.baseline_summary, self.corrected_summary, self.current_summary
        )
        self.compare_headline_var.set(compare_display["headline"])
        self.compare_detail_var.set(compare_display["detail"])
        self.compare_left_var.set(compare_display["left"])
        self.compare_right_var.set(compare_display["right"])

        if self.baseline_summary is not None and self.corrected_summary is not None:
            baseline_label = _summary_label(self.baseline_summary, "원본")
            corrected_label = _summary_label(self.corrected_summary, "보정안")
            self._set_overlay_panel(
                side="left",
                title=self._build_preview_title(self.baseline_summary, baseline_label),
                summary=self.baseline_summary,
                empty_text=self._build_overlay_placeholder(baseline_label, self.baseline_summary),
            )
            self._set_overlay_panel(
                side="right",
                title=self._build_preview_title(self.corrected_summary, corrected_label),
                summary=self.corrected_summary,
                empty_text=self._build_overlay_placeholder(corrected_label, self.corrected_summary),
            )
            return

        current_title = "현재 결과"
        if self.current_summary is not None:
            current_label = _summary_label(
                self.current_summary,
                "보정안" if self.current_summary.get("variant") == "corrected" else "원본",
            )
            current_title = f"현재 결과 · {current_label}"
        self._set_overlay_panel(
            side="left",
            title=self._build_preview_title(self.current_summary, current_title),
            summary=self.current_summary,
            empty_text=self._build_overlay_placeholder("현재 결과", self.current_summary),
        )
        self._set_overlay_panel(
            side="right",
            title="비교 없음",
            summary=None,
            empty_text="보정 비교를 실행하면 원본/보정안을 나란히 표시합니다",
        )

    def _handle_result_double_click(self, event: tk.Event) -> None:
        row_id = self.result_tree.identify_row(event.y)
        if not row_id:
            return
        column_id = self.result_tree.identify_column(event.x)
        self.result_tree.selection_set(row_id)
        record = result_record_from_tree_item(self.result_tree.item(row_id), row_id)
        target = resolve_result_open_target(column_id, record, self.current_summary)
        if not target.exists():
            self._show_error(f"열 대상 파일/폴더를 찾을 수 없습니다: {target}")
            return
        try:
            self._open_path_in_host(target)
        except Exception as exc:
            self._show_error(str(exc))
            return
        self.log_text.insert(tk.END, f"result_open={target}\n")
        self.log_text.see(tk.END)

    def _pick_ui_font_family(self) -> str:
        candidates = [
            "Noto Sans CJK KR",
            "Noto Sans KR",
            "NanumBarunGothic",
            "NanumGothic",
            "Malgun Gothic",
            "Apple SD Gothic Neo",
            "Arial Unicode MS",
            "DejaVu Sans",
        ]

        available: set[str] = set()
        if tkfont is not None:
            try:
                available.update(str(name) for name in tkfont.families(self.root))
            except tk.TclError:
                pass

        if not available:
            try:
                proc = subprocess.run(
                    ["fc-list", ":lang=ko", "family"],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                for line in proc.stdout.splitlines():
                    for name in line.split(","):
                        name = name.strip()
                        if name:
                            available.add(name)
            except Exception:
                pass

        default_family = "TkDefaultFont"
        if tkfont is not None:
            try:
                default_family = str(tkfont.nametofont("TkDefaultFont").actual("family"))
            except tk.TclError:
                pass

        if default_family:
            candidates.insert(0, default_family)

        for family in candidates:
            if family in available:
                return family
        return default_family

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")

        bg = "#f4f6f8"
        panel = "#ffffff"
        border = "#d7dde3"
        accent = "#0f5c4d"
        text = "#1f2933"
        subtext = "#52606d"
        family = self._pick_ui_font_family()
        self.ui_font_family = family

        base_font = None
        text_font = None
        heading_font = None
        metric_font = None
        tab_font = None
        if tkfont is not None:
            try:
                base_font = tkfont.nametofont("TkDefaultFont")
                base_font.configure(family=family, size=11)
                text_font = tkfont.Font(root=self.root, family=family, size=11)
                heading_font = tkfont.Font(root=self.root, family=family, size=18, weight="bold")
                metric_font = tkfont.Font(root=self.root, family=family, size=12, weight="bold")
                tab_font = tkfont.Font(root=self.root, family=family, size=12, weight="bold")
                self.root.option_add("*Font", base_font)
            except tk.TclError:
                base_font = None

        self.root.configure(bg=bg)
        style.configure(".", background=bg, foreground=text)
        style.configure("TFrame", background=bg)
        style.configure("Panel.TLabelframe", background=bg, bordercolor=border)
        style.configure("Panel.TLabelframe.Label", background=bg, foreground=text)
        style.configure("Metric.TLabelframe", background=bg, bordercolor=border)
        style.configure("Metric.TLabelframe.Label", background=bg, foreground=subtext)
        style.configure("TLabel", background=bg, foreground=text)
        style.configure("Muted.TLabel", background=bg, foreground=subtext)
        style.configure("Heading.TLabel", background=bg, foreground=text, font=heading_font or (family, 18, "bold"))
        style.configure("Subheading.TLabel", background=bg, foreground=subtext, font=text_font or (family, 11))
        style.configure("MetricValue.TLabel", background=bg, foreground=text, font=metric_font or (family, 12, "bold"))
        style.configure("CompareHeadline.TLabel", background=panel, foreground=text, font=metric_font or (family, 12, "bold"))
        style.configure("CompareDetail.TLabel", background=panel, foreground=subtext)
        style.configure("CompareStat.TLabel", background=panel, foreground=text)
        style.configure("IdleBadge.TLabel", background="#e7eef4", foreground="#334e68", padding=(10, 5))
        style.configure("BusyBadge.TLabel", background="#fff3cd", foreground="#8a5a00", padding=(10, 5))
        style.configure("OverlayHint.TLabel", background=panel, foreground=subtext)
        style.configure("TNotebook", background=bg, tabmargins=(0, 0, 0, 0))
        style.configure("TNotebook.Tab", padding=(22, 12), font=tab_font or (family, 12, "bold"))
        style.map(
            "TNotebook.Tab",
            background=[("selected", "#ffffff"), ("!selected", "#e7eef4")],
            foreground=[("selected", text), ("!selected", subtext)],
        )
        style.configure("TButton", padding=(12, 7))
        style.configure("Accent.TButton", padding=(14, 9), background=accent, foreground="white")
        style.map(
            "Accent.TButton",
            background=[("active", "#0b4a3d"), ("pressed", "#08382f")],
            foreground=[("disabled", "#d9e2ec"), ("!disabled", "white")],
        )
        style.configure("Treeview", rowheight=28, fieldbackground=panel, background=panel)
        style.configure("Treeview.Heading", font=metric_font or (family, 12, "bold"))

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)

        header = ttk.Frame(self.root, padding=(12, 12, 12, 6))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="용접 경로 생성 데모", style="Heading.TLabel").grid(
            row=0, column=0, sticky="w"
        )

        status_strip = ttk.Frame(self.root, padding=(12, 0, 12, 8))
        status_strip.grid(row=1, column=0, sticky="ew")
        status_strip.columnconfigure(0, weight=1)
        status_strip.columnconfigure(1, weight=1)
        status_strip.columnconfigure(2, weight=2)
        status_strip.columnconfigure(3, weight=2)

        status_card = ttk.Labelframe(status_strip, text="상태", style="Metric.TLabelframe", padding=10)
        status_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        ttk.Label(status_card, textvariable=self.status_var, style="MetricValue.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self.progress_badge_label = ttk.Label(
            status_card,
            textvariable=self.progress_badge_var,
            style="IdleBadge.TLabel",
        )
        self.progress_badge_label.grid(row=1, column=0, sticky="w", pady=(8, 0))

        capture_card = ttk.Labelframe(status_strip, text="선택 캡처", style="Metric.TLabelframe", padding=10)
        capture_card.grid(row=0, column=1, sticky="nsew", padx=3)
        ttk.Label(capture_card, textvariable=self.capture_var, style="MetricValue.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(capture_card, textvariable=self.camera_status_var, style="Muted.TLabel").grid(
            row=1, column=0, sticky="w", pady=(6, 0)
        )

        output_card = ttk.Labelframe(status_strip, text="출력 폴더", style="Metric.TLabelframe", padding=10)
        output_card.grid(row=0, column=2, sticky="nsew", padx=3)
        ttk.Label(output_card, textvariable=self.output_dir_var, style="Muted.TLabel").grid(
            row=0, column=0, sticky="w"
        )

        review_card = ttk.Labelframe(status_strip, text="검토 / 서비스", style="Metric.TLabelframe", padding=10)
        review_card.grid(row=0, column=3, sticky="nsew", padx=(6, 0))
        ttk.Label(review_card, textvariable=self.review_var, style="Muted.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(review_card, textvariable=self.mechviz_service_var, style="Muted.TLabel").grid(
            row=1, column=0, sticky="w", pady=(6, 0)
        )

        notebook = ttk.Notebook(self.root)
        notebook.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.main_notebook = notebook

        capture_tab = ttk.Frame(notebook, padding=12)
        path_tab = ttk.Frame(notebook, padding=12)
        integration_tab = ttk.Frame(notebook, padding=12)
        notebook.add(capture_tab, text="1. 촬영")
        notebook.add(path_tab, text="2. 경로")
        notebook.add(integration_tab, text="3. 연동")

        capture_tab.columnconfigure(0, weight=0)
        capture_tab.columnconfigure(1, weight=1)
        capture_tab.rowconfigure(1, weight=1)
        ttk.Label(
            capture_tab,
            text="기준 캡처를 선택하고 카메라 촬영 또는 ICP 등록까지 먼저 정리합니다.",
            style="Subheading.TLabel",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        capture_controls = ttk.Frame(capture_tab)
        capture_controls.grid(row=1, column=0, sticky="nsw", padx=(0, 12))
        capture_controls.columnconfigure(0, weight=1)

        capture_frame = ttk.Labelframe(capture_controls, text="캡처 선택", style="Panel.TLabelframe", padding=10)
        capture_frame.grid(row=0, column=0, sticky="ew")
        capture_frame.columnconfigure(0, weight=1)

        self.capture_box = ttk.Combobox(
            capture_frame,
            textvariable=self.capture_var,
            values=self.capture_labels,
            state="readonly",
            width=28,
        )
        self.capture_box.grid(row=0, column=0, sticky="ew")
        self.capture_box.bind("<<ComboboxSelected>>", lambda _e: self._refresh_capture_notes())
        self.icp_register_button = ttk.Button(
            capture_frame,
            text="ICP 등록",
            command=self._start_register_icp,
        )
        self.icp_register_button.grid(row=0, column=1, sticky="e", padx=(8, 0))
        ttk.Button(capture_frame, text="목록 새로고침", command=self._refresh_capture_entries).grid(
            row=0, column=2, sticky="e", padx=(8, 0)
        )

        camera_frame = ttk.Labelframe(capture_controls, text="카메라", style="Panel.TLabelframe", padding=10)
        camera_frame.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        camera_frame.columnconfigure(0, weight=1)
        camera_frame.columnconfigure(1, weight=0)

        ttk.Label(camera_frame, text="카메라 IP", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(camera_frame, textvariable=self.camera_ip_var).grid(
            row=1, column=0, sticky="ew", pady=(2, 8)
        )
        ttk.Button(camera_frame, text="저장", command=self._save_camera_settings).grid(
            row=1, column=1, sticky="e", padx=(8, 0), pady=(2, 8)
        )
        ttk.Button(camera_frame, text="검색", command=self._start_camera_discover).grid(
            row=2, column=0, sticky="ew"
        )
        ttk.Button(camera_frame, text="촬영", command=self._start_camera_capture).grid(
            row=2, column=1, sticky="ew", padx=(8, 0)
        )
        ttk.Label(camera_frame, text="캡처 저장 경로", style="Muted.TLabel").grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(10, 0)
        )
        ttk.Label(camera_frame, textvariable=self.captures_dir_var, style="Muted.TLabel").grid(
            row=4, column=0, columnspan=2, sticky="w"
        )
        ttk.Label(camera_frame, textvariable=self.camera_status_var, style="Muted.TLabel").grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(8, 0)
        )

        notes_frame = ttk.Labelframe(capture_tab, text="캡처 메모", style="Panel.TLabelframe", padding=10)
        notes_frame.grid(row=1, column=1, sticky="nsew")
        notes_frame.columnconfigure(0, weight=1)
        notes_frame.rowconfigure(0, weight=1)
        self.notes_text = tk.Text(
            notes_frame,
            width=34,
            height=16,
            wrap="word",
            relief="flat",
            bg="#ffffff",
            font=(getattr(self, "ui_font_family", "TkDefaultFont"), 10),
        )
        self.notes_text.grid(row=0, column=0, sticky="nsew")
        notes_scroll = ttk.Scrollbar(notes_frame, orient="vertical", command=self.notes_text.yview)
        notes_scroll.grid(row=0, column=1, sticky="ns")
        self.notes_text.configure(yscrollcommand=notes_scroll.set)

        path_tab.columnconfigure(0, weight=0)
        path_tab.columnconfigure(1, weight=1)
        path_tab.rowconfigure(1, weight=1)
        ttk.Label(
            path_tab,
            text="seam 선택, 경로 생성, 보정 비교와 산출물 확인을 한 흐름으로 묶었습니다.",
            style="Subheading.TLabel",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        path_controls = ttk.Frame(path_tab)
        path_controls.grid(row=1, column=0, sticky="nsw", padx=(0, 12))
        path_controls.columnconfigure(0, weight=1)
        path_controls.rowconfigure(1, weight=1)

        settings_frame = ttk.Labelframe(path_controls, text="실행 설정", style="Panel.TLabelframe", padding=10)
        settings_frame.grid(row=0, column=0, sticky="ew")
        settings_frame.columnconfigure(0, weight=1)

        ttk.Label(settings_frame, text="간격 (mm)", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(settings_frame, textvariable=self.step_var, width=10).grid(
            row=1, column=0, sticky="w", pady=(2, 10)
        )
        ttk.Checkbutton(
            settings_frame,
            text="실험용 edge / hybrid 보정 사용",
            variable=self.edge_snap_var,
        ).grid(row=2, column=0, sticky="w")

        seams_frame = ttk.Labelframe(path_controls, text="Seam 후보", style="Panel.TLabelframe", padding=10)
        seams_frame.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        seams_frame.columnconfigure(0, weight=1)
        seams_frame.rowconfigure(0, weight=1)

        self.seam_tree = ttk.Treeview(
            seams_frame,
            columns=("description",),
            show="tree headings",
            selectmode="extended",
            height=10,
        )
        self.seam_tree.heading("#0", text="이름")
        self.seam_tree.heading("description", text="설명")
        self.seam_tree.column("#0", width=130, anchor="w")
        self.seam_tree.column("description", width=220, anchor="w")
        self.seam_tree.grid(row=0, column=0, sticky="nsew")
        seam_scroll = ttk.Scrollbar(seams_frame, orient="vertical", command=self.seam_tree.yview)
        seam_scroll.grid(row=0, column=1, sticky="ns")
        self.seam_tree.configure(yscrollcommand=seam_scroll.set)
        for seam_name, seam_def in SEAM_CANDIDATES.items():
            self.seam_tree.insert("", tk.END, iid=seam_name, text=seam_name, values=(seam_def["description"],))

        default_names = ["U1_right", "U2_left"]
        for name in SEAM_CANDIDATES:
            if name in default_names:
                self.seam_tree.selection_add(name)

        seam_btn_frame = ttk.Frame(seams_frame)
        seam_btn_frame.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        ttk.Button(seam_btn_frame, text="전체 선택", command=self._select_all_seams).pack(side="left", padx=(0, 4))
        ttk.Button(seam_btn_frame, text="전체 해제", command=self._deselect_all_seams).pack(side="left")

        actions_frame = ttk.Frame(path_controls)
        actions_frame.grid(row=2, column=0, sticky="ew", pady=(12, 6))
        actions_frame.columnconfigure(0, weight=1)
        actions_frame.columnconfigure(1, weight=1)
        ttk.Button(actions_frame, text="경로 생성 실행", style="Accent.TButton", command=self._start_run).grid(
            row=0, column=0, sticky="ew", padx=(0, 4)
        )
        ttk.Button(actions_frame, text="보정 미리보기", command=self._start_correction_preview).grid(
            row=0, column=1, sticky="ew", padx=(4, 0)
        )
        ttk.Button(actions_frame, text="Snap 정책 비교", command=self._start_snap_policy_preview).grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0)
        )

        review_frame = ttk.Labelframe(path_controls, text="보정 검토", style="Panel.TLabelframe", padding=10)
        review_frame.grid(row=3, column=0, sticky="ew")
        review_frame.columnconfigure(0, weight=1)
        review_frame.columnconfigure(1, weight=1)
        ttk.Button(review_frame, text="보정안 적용", command=self._apply_corrected).grid(
            row=0, column=0, sticky="ew", padx=(0, 4)
        )
        ttk.Button(review_frame, text="원본 유지", command=self._keep_original).grid(
            row=0, column=1, sticky="ew", padx=(4, 0)
        )
        ttk.Label(review_frame, textvariable=self.review_var, style="Muted.TLabel").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(8, 0)
        )

        path_results = ttk.Frame(path_tab)
        path_results.grid(row=1, column=1, sticky="nsew")
        path_results.columnconfigure(0, weight=1)
        path_results.rowconfigure(2, weight=1)
        ttk.Label(
            path_results,
            text="실행 결과를 확인하고 더블클릭으로 pose/1100/출력 폴더를 바로 열 수 있습니다.",
            style="Muted.TLabel",
        ).grid(row=0, column=0, sticky="w")

        result_frame = ttk.Labelframe(path_results, text="실행 결과 표", style="Panel.TLabelframe", padding=10)
        result_frame.grid(row=1, column=0, sticky="ew", pady=(8, 12))
        result_frame.columnconfigure(0, weight=1)

        columns = ("seam", "poses", "mean", "p90", "max", "pose_csv", "txt_1100")
        self.result_tree = ttk.Treeview(result_frame, columns=columns, show="headings", height=7)
        self.result_tree.heading("seam", text="Seam")
        self.result_tree.heading("poses", text="포즈 수")
        self.result_tree.heading("mean", text="평균 NN")
        self.result_tree.heading("p90", text="P90 NN")
        self.result_tree.heading("max", text="최대 NN")
        self.result_tree.heading("pose_csv", text="Pose CSV")
        self.result_tree.heading("txt_1100", text="1100")
        self.result_tree.column("seam", width=110, anchor="w")
        self.result_tree.column("poses", width=70, anchor="center")
        self.result_tree.column("mean", width=90, anchor="center")
        self.result_tree.column("p90", width=90, anchor="center")
        self.result_tree.column("max", width=90, anchor="center")
        self.result_tree.column("pose_csv", width=260)
        self.result_tree.column("txt_1100", width=260)
        self.result_tree.grid(row=0, column=0, sticky="ew")
        result_scroll = ttk.Scrollbar(result_frame, orient="vertical", command=self.result_tree.yview)
        result_scroll.grid(row=0, column=1, sticky="ns")
        self.result_tree.configure(yscrollcommand=result_scroll.set)
        self.result_tree.bind("<Double-1>", self._handle_result_double_click)

        preview_pane = ttk.Panedwindow(path_results, orient=tk.VERTICAL)
        preview_pane.grid(row=2, column=0, sticky="nsew")

        image_frame = ttk.Labelframe(preview_pane, text="오버레이 비교", padding=8)
        preview_pane.add(image_frame, weight=3)
        image_frame.columnconfigure(0, weight=1)
        image_frame.rowconfigure(1, weight=1)

        compare_frame = ttk.Frame(image_frame, padding=(4, 2, 4, 10))
        compare_frame.grid(row=0, column=0, columnspan=2, sticky="ew")
        compare_frame.columnconfigure(0, weight=1)
        compare_frame.columnconfigure(1, weight=1)
        ttk.Label(compare_frame, textvariable=self.compare_headline_var, style="CompareHeadline.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        ttk.Label(compare_frame, textvariable=self.compare_detail_var, style="CompareDetail.TLabel").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(4, 0)
        )
        ttk.Label(compare_frame, textvariable=self.compare_left_var, style="CompareStat.TLabel").grid(
            row=2, column=0, sticky="w", pady=(6, 0), padx=(0, 8)
        )
        ttk.Label(compare_frame, textvariable=self.compare_right_var, style="CompareStat.TLabel").grid(
            row=2, column=1, sticky="w", pady=(6, 0), padx=(8, 0)
        )

        image_frame.columnconfigure(0, weight=1)
        image_frame.columnconfigure(1, weight=1)
        image_frame.rowconfigure(1, weight=1)

        left_overlay_frame = ttk.Labelframe(image_frame, text=self.preview_left_title_var.get(), padding=6)
        left_overlay_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 6))
        left_overlay_frame.columnconfigure(0, weight=1)
        left_overlay_frame.rowconfigure(0, weight=1)
        self.overlay_left_frame = left_overlay_frame
        self.overlay_left_canvas = tk.Canvas(left_overlay_frame, bg="#2b2b2b", highlightthickness=0)
        self.overlay_left_canvas.grid(row=0, column=0, sticky="nsew")
        self._bind_overlay_canvas(self.overlay_left_canvas, "left")

        right_overlay_frame = ttk.Labelframe(image_frame, text=self.preview_right_title_var.get(), padding=6)
        right_overlay_frame.grid(row=1, column=1, sticky="nsew", padx=(6, 0))
        right_overlay_frame.columnconfigure(0, weight=1)
        right_overlay_frame.rowconfigure(0, weight=1)
        self.overlay_right_frame = right_overlay_frame
        self.overlay_right_canvas = tk.Canvas(right_overlay_frame, bg="#2b2b2b", highlightthickness=0)
        self.overlay_right_canvas.grid(row=0, column=0, sticky="nsew")
        self._bind_overlay_canvas(self.overlay_right_canvas, "right")

        integration_tab.columnconfigure(0, weight=1)
        integration_tab.rowconfigure(2, weight=1)
        ttk.Label(
            integration_tab,
            text="DTS 자동 검증과 Mech-Viz 연동은 경로 탭에서 선택한 결과 행을 기준으로 실행됩니다.",
            style="Subheading.TLabel",
        ).grid(row=0, column=0, sticky="w", pady=(0, 10))

        actions_right = ttk.Labelframe(integration_tab, text="연동 작업", style="Panel.TLabelframe", padding=10)
        actions_right.grid(row=1, column=0, sticky="ew")
        actions_right.columnconfigure(0, weight=1)
        actions_right.columnconfigure(1, weight=1)
        ttk.Button(actions_right, text="DTS 자동 검증", command=self._start_dts_e2e).grid(
            row=0, column=0, sticky="ew", padx=(0, 4)
        )
        ttk.Button(actions_right, text="Mech-Viz 내보내기", command=self._start_mechviz_export).grid(
            row=0, column=1, sticky="ew", padx=(4, 0)
        )
        ttk.Button(actions_right, text="서비스 시작", command=self._start_mechviz_service).grid(
            row=1, column=0, sticky="ew", padx=(0, 4), pady=(8, 0)
        )
        ttk.Button(actions_right, text="서비스 중지", command=self._stop_mechviz_service).grid(
            row=1, column=1, sticky="ew", padx=(4, 0), pady=(8, 0)
        )
        ttk.Button(actions_right, text="프로젝트 열기", command=self._open_mechviz_project).grid(
            row=2, column=0, sticky="ew", padx=(0, 4), pady=(8, 0)
        )
        ttk.Button(
            actions_right,
            text="시뮬레이션 실행",
            style="Accent.TButton",
            command=self._start_mechviz_simulate,
        ).grid(row=2, column=1, sticky="ew", padx=(4, 0), pady=(8, 0))

        log_frame = ttk.Labelframe(integration_tab, text="실행 로그", style="Panel.TLabelframe", padding=8)
        log_frame.grid(row=2, column=0, sticky="nsew", pady=(12, 0))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_text = tk.Text(
            log_frame,
            wrap="word",
            relief="flat",
            bg="#ffffff",
            font=(getattr(self, "ui_font_family", "TkDefaultFont"), 10),
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=log_scroll.set)

    def _refresh_capture_notes(self) -> None:
        capture_id = self._selected_capture_id()
        if not capture_id:
            self.notes_text.delete("1.0", tk.END)
            self.notes_text.insert("1.0", "선택된 캡처가 없습니다.")
            self.icp_register_button.configure(state="disabled")
            return
        entry = self.capture_entries[capture_id]
        capture_info = describe_capture_entry(capture_id, entry, self.registry)
        icp_path = entry.get("icp_transform_npy") or "(ICP 등록 필요)"
        lines = [
            f"캡처 ID: {capture_id}",
            f"상태: {capture_info['status_label']}",
            f"원본 PLY: {entry['raw_capture_ply']}",
            f"ICP: {icp_path}",
            f"평가용 클라우드: {entry['canonical_nn_evaluation_cloud']}",
            f"출처: {capture_info['origin']}",
            "",
        ]
        if capture_info["icp_register_reason"]:
            lines.append(f"- ICP 등록: {capture_info['icp_register_reason']}")
        lines.extend(f"- {note}" for note in entry.get("notes", []))
        self.notes_text.delete("1.0", tk.END)
        self.notes_text.insert("1.0", "\n".join(lines))
        self.icp_register_button.configure(
            state="normal" if capture_info["allow_icp_register"] else "disabled"
        )

    def _refresh_capture_entries(self, select_capture_id: str | None = None) -> None:
        self.live_registry = load_live_registry(
            DEFAULT_LIVE_REGISTRY,
            reference_pcd=self.registry.get("reference_pcd"),
        )
        captures_dir = Path(self.captures_dir_var.get().strip() or get_captures_dir())
        self.capture_ids, self.capture_entries = merge_capture_entries(
            self._combined_registry(),
            captures_dir,
        )
        self._rebuild_capture_labels()
        self.capture_box.configure(values=self.capture_labels)

        if select_capture_id and select_capture_id in self.capture_entries:
            self.capture_var.set(self.capture_id_to_label.get(select_capture_id, select_capture_id))
        elif self._selected_capture_id() not in self.capture_entries:
            default_label = self.capture_id_to_label.get(self.capture_ids[-1], "") if self.capture_ids else ""
            self.capture_var.set(default_label)

        self._refresh_capture_notes()

    def _rebuild_capture_labels(self) -> None:
        self.capture_id_to_label: dict[str, str] = {}
        self.capture_label_to_id: dict[str, str] = {}
        for cid in self.capture_ids:
            entry = self.capture_entries[cid]
            label = capture_display_label(cid, entry)
            self.capture_id_to_label[cid] = label
            self.capture_label_to_id[label] = cid
        self.capture_labels = [self.capture_id_to_label[cid] for cid in self.capture_ids]

    def _selected_capture_id(self) -> str:
        label = self.capture_var.get()
        return self.capture_label_to_id.get(label, label)

    def _combined_registry(self) -> dict[str, Any]:
        captures = dict(self.registry.get("captures", {}))
        captures.update(self.live_registry.get("captures", {}))
        return {
            "reference_pcd": self.registry.get("reference_pcd"),
            "captures": captures,
        }

    def _selected_seams(self) -> list[str]:
        return list(self.seam_tree.selection())

    def _select_all_seams(self) -> None:
        self.seam_tree.selection_set(list(SEAM_CANDIDATES.keys()))

    def _deselect_all_seams(self) -> None:
        self.seam_tree.selection_set([])

    def _selected_result_record(self) -> dict[str, Any] | None:
        selection = list(self.result_tree.selection())
        if not selection:
            children = list(self.result_tree.get_children())
            if len(children) == 1:
                selection = children
            else:
                self._show_error("먼저 결과 행을 선택해 주세요.")
                return None
        item_id = selection[0]
        item = self.result_tree.item(item_id)
        return result_record_from_tree_item(item, item_id)

    def _to_windows_unc_path(self, path: Path) -> str:
        result = subprocess.run(
            ["wslpath", "-w", str(path)],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    def _to_wsl_path_from_windows(self, path: str) -> Path:
        result = subprocess.run(
            ["wslpath", "-u", path],
            check=True,
            capture_output=True,
            text=True,
        )
        return Path(result.stdout.strip())

    def _validate_run_request(self) -> tuple[str, dict[str, Any], list[str], float] | None:
        seams = self._selected_seams()
        if not seams:
            self._show_error("최소 한 개 이상의 seam를 선택해 주세요.")
            return None

        try:
            step_mm = float(self.step_var.get())
            if step_mm <= 0:
                raise ValueError
        except ValueError:
            self._show_error("간격 값은 0보다 큰 숫자여야 합니다.")
            return None

        capture_id = self._selected_capture_id()
        capture_entry = self.capture_entries[capture_id]
        icp_path = capture_entry.get("icp_transform_npy")
        if not icp_path:
            self._show_error(
                "이 캡처는 아직 ICP가 등록되지 않았습니다. 촬영/불러오기는 끝났지만 먼저 ICP 등록을 해주세요."
            )
            return None
        if not Path(icp_path).exists():
            self._show_error(f"ICP 변환 파일을 찾을 수 없습니다: {icp_path}")
            return None
        return capture_id, capture_entry, seams, step_mm

    def _save_camera_settings(self) -> None:
        self.camera_config["camera_ip"] = self.camera_ip_var.get().strip()
        self.camera_config["captures_dir"] = self.captures_dir_var.get().strip() or str(get_captures_dir())
        save_camera_config(self.camera_config, DEFAULT_CAMERA_CONFIG)
        self.camera_status_var.set("카메라 설정 저장 완료")
        self._refresh_capture_entries()

    def _start_camera_discover(self) -> None:
        if self.camera_thread and self.camera_thread.is_alive():
            self._show_error("카메라 작업이 이미 실행 중입니다.")
            return
        if not self._ensure_idle():
            return
        self.camera_status_var.set("카메라 검색 중...")
        self.camera_thread = threading.Thread(target=self._camera_discover_worker, daemon=True)
        self.camera_thread.start()
        self._refresh_action_state()

    def _start_camera_capture(self) -> None:
        if self.camera_thread and self.camera_thread.is_alive():
            self._show_error("카메라 작업이 이미 실행 중입니다.")
            return
        if not self._ensure_idle():
            return
        self._save_camera_settings()
        self.camera_status_var.set("촬영 중...")
        self.log_text.insert(tk.END, "camera_capture=촬영 시작\n")
        self.log_text.see(tk.END)
        self.camera_thread = threading.Thread(target=self._camera_capture_worker, daemon=True)
        self.camera_thread.start()
        self._refresh_action_state()

    def _start_register_icp(self) -> None:
        if self.icp_thread and self.icp_thread.is_alive():
            self._show_error("ICP 등록이 이미 실행 중입니다.")
            return
        if not self._ensure_idle():
            return

        capture_id = self._selected_capture_id()
        if not capture_id:
            self._show_error("먼저 캡처를 선택해 주세요.")
            return

        entry = self.capture_entries[capture_id]
        capture_info = describe_capture_entry(capture_id, entry, self.registry)
        if not capture_info["allow_icp_register"]:
            self._show_error(capture_info["icp_register_reason"])
            return

        raw_capture_ply = Path(entry["raw_capture_ply"])
        if not raw_capture_ply.exists():
            self._show_error(f"원본 캡처 파일을 찾을 수 없습니다: {raw_capture_ply}")
            return

        self.status_var.set("ICP 등록 중...")
        self.log_text.insert(tk.END, f"icp_register=시작 capture={capture_id}\n")
        self.log_text.see(tk.END)
        self.icp_thread = threading.Thread(
            target=self._register_icp_worker,
            args=(capture_id, raw_capture_ply),
            daemon=True,
        )
        self.icp_thread.start()
        self._refresh_action_state()

    def _start_mechviz_export(self) -> None:
        if self.export_thread and self.export_thread.is_alive():
            self._show_error("Mech-Viz 내보내기가 이미 실행 중입니다.")
            return
        if not self._ensure_idle():
            return
        record = self._selected_result_record()
        if record is None:
            return
        self.status_var.set("Mech-Viz 내보내기 중...")
        self.log_text.insert(tk.END, f"mechviz_export=시작 seam={record['name']}\n")
        self.log_text.see(tk.END)
        self.export_thread = threading.Thread(
            target=self._mechviz_export_worker,
            args=(record,),
            daemon=True,
        )
        self.export_thread.start()
        self._refresh_action_state()

    def _start_mechviz_service(self) -> None:
        if self.mechviz_service_thread and self.mechviz_service_thread.is_alive():
            self._show_error("Mech-Viz 서비스 작업이 이미 실행 중입니다.")
            return
        if not self._ensure_idle():
            return
        # No blocking probe here — just check the cached PID.
        if self.mechviz_service_pid is not None:
            self._show_error("이미 실행 중인 Mech-Viz 서비스가 있습니다. 먼저 중지해 주세요.")
            return
        record = self._selected_result_record()
        if record is None:
            return
        self.status_var.set("Mech-Viz 서비스 시작 중...")
        self.log_text.insert(tk.END, f"mechviz_service=시작 seam={record['name']}\n")
        self.log_text.see(tk.END)
        self.mechviz_service_thread = threading.Thread(
            target=self._mechviz_service_start_worker,
            args=(record,),
            daemon=True,
        )
        self.mechviz_service_thread.start()
        self._refresh_action_state()

    def _stop_mechviz_service(self) -> None:
        if self.mechviz_service_thread and self.mechviz_service_thread.is_alive():
            self._show_error("Mech-Viz 서비스 작업이 이미 실행 중입니다.")
            return
        if not self._ensure_idle():
            return
        # No blocking probe — just use cached PID. If the process already died,
        # taskkill will simply report "not found" and we clear the PID anyway.
        if self.mechviz_service_pid is None:
            self._show_error("현재 실행 중인 Mech-Viz 서비스가 없습니다.")
            return
        pid = self.mechviz_service_pid
        self.status_var.set("Mech-Viz 서비스 중지 중...")
        self.log_text.insert(tk.END, f"mechviz_service=중지 pid={pid}\n")
        self.log_text.see(tk.END)
        self.mechviz_service_thread = threading.Thread(
            target=self._mechviz_service_stop_worker,
            args=(pid,),
            daemon=True,
        )
        self.mechviz_service_thread.start()
        self._refresh_action_state()

    def _start_mechviz_simulate(self) -> None:
        """One-click: export → service start → project open → trigger simulation."""
        if self.mechviz_simulate_thread and self.mechviz_simulate_thread.is_alive():
            self._show_error("Mech-Viz 시뮬레이션이 이미 실행 중입니다.")
            return
        if not self._ensure_idle():
            return
        # Skip _sync_mechviz_service_state here — the blocking probe (up to 10s)
        # freezes the UI and can falsely reset the PID. The simulate worker will
        # reuse an existing service if mechviz_service_pid is set, or start a new
        # one otherwise.
        record = self._selected_result_record()
        if record is None:
            return
        self.status_var.set("Mech-Viz 시뮬레이션 준비 중...")
        self.log_text.insert(tk.END, f"mechviz_simulate=시작 seam={record['name']}\n")
        self.log_text.see(tk.END)
        self.mechviz_simulate_thread = threading.Thread(
            target=self._mechviz_simulate_worker,
            args=(record, self.mechviz_service_pid),
            daemon=True,
        )
        self.mechviz_simulate_thread.start()
        self._refresh_action_state()

    def _open_mechviz_project(self) -> None:
        if self.mechviz_open_thread and self.mechviz_open_thread.is_alive():
            self._show_error("Mech-Viz 프로젝트 열기가 이미 실행 중입니다.")
            return
        if not self._ensure_idle():
            return
        self.status_var.set("Mech-Viz 프로젝트 여는 중...")
        self.log_text.insert(tk.END, "mechviz_project=열기 시작\n")
        self.log_text.see(tk.END)
        self.mechviz_open_thread = threading.Thread(
            target=self._mechviz_project_open_worker,
            daemon=True,
        )
        self.mechviz_open_thread.start()
        self._refresh_action_state()

    def _start_dts_e2e(self) -> None:
        if self.e2e_thread and self.e2e_thread.is_alive():
            self._show_error("DTS 자동 검증이 이미 실행 중입니다.")
            return
        if not self._ensure_idle():
            return
        record = self._selected_result_record()
        if record is None:
            return
        payload_path = Path(record["txt_1100"])
        if not payload_path.exists():
            self._show_error(f"1100 payload 파일을 찾을 수 없습니다: {payload_path}")
            return
        self.status_var.set("DTS 자동 검증 실행 중...")
        self.log_text.insert(tk.END, f"dts_e2e=시작 seam={record['name']}\n")
        self.log_text.see(tk.END)
        self.e2e_thread = threading.Thread(
            target=self._dts_e2e_worker,
            args=(record,),
            daemon=True,
        )
        self.e2e_thread.start()
        self._refresh_action_state()

    def _camera_discover_worker(self) -> None:
        try:
            cameras = discover_cameras()
            self.ui_queue.put(("camera_discovered", cameras))
        except Exception:
            self.ui_queue.put(("camera_error", traceback.format_exc()))

    def _camera_capture_worker(self) -> None:
        try:
            result = capture_bundle(
                camera_ip=self.camera_ip_var.get().strip() or None,
                output_dir=Path(self.captures_dir_var.get().strip() or get_captures_dir()),
                tag=self.camera_config.get("default_capture_tag", "gui"),
                config=self.camera_config,
            )
            self.ui_queue.put(("camera_capture_done", result))
        except Exception:
            self.ui_queue.put(("camera_error", traceback.format_exc()))

    def _register_icp_worker(self, capture_id: str, raw_capture_ply: Path) -> None:
        try:
            result = register_live_capture_icp(
                raw_capture_ply=raw_capture_ply,
                capture_id=capture_id,
            )
            self.ui_queue.put(("icp_registered", result))
        except Exception:
            self.ui_queue.put(("icp_error", traceback.format_exc()))

    def _export_mechviz_files(self, pose_csv: Path) -> dict[str, str]:
        """No intermediate files needed — the service reads pose.csv directly."""
        return {
            "pose_csv": str(pose_csv),
        }

    def _mechviz_export_worker(self, record: dict[str, Any]) -> None:
        try:
            pose_csv = Path(record["pose_csv"])
            outputs = self._export_mechviz_files(pose_csv)
            self.ui_queue.put(
                (
                    "mechviz_exported",
                    {
                        "seam": record["name"],
                        **outputs,
                    },
                )
            )
        except Exception:
            self.ui_queue.put(("mechviz_export_error", traceback.format_exc()))

    def _mechviz_service_start_worker(self, record: dict[str, Any]) -> None:
        try:
            launcher_script = self._to_windows_unc_path(SCRIPTS_DIR / "start_mechviz_service.ps1")
            service_script = self._to_windows_unc_path(SCRIPTS_DIR / "viz_outer_move_service.py")
            pose_csv_win = self._to_windows_unc_path(Path(record["pose_csv"]))
            result = start_outer_move_service(
                windows_launcher_script=launcher_script,
                windows_service_script=service_script,
                windows_pose_csv_path=pose_csv_win,
                config=self.mechviz_config,
            )
            result.update(
                {
                    "seam": record["name"],
                    "pose_csv": record["pose_csv"],
                }
            )
            self.ui_queue.put(("mechviz_service_started", result))
        except Exception:
            self.ui_queue.put(("mechviz_service_error", traceback.format_exc()))

    def _mechviz_service_stop_worker(self, pid: int) -> None:
        try:
            result = stop_outer_move_service(pid)
            self.ui_queue.put(("mechviz_service_stopped", result))
        except Exception:
            self.ui_queue.put(("mechviz_service_error", traceback.format_exc()))

    def _mechviz_simulate_worker(self, record: dict[str, Any], existing_service_pid: int | None = None) -> None:
        """Chain: service start → project open → trigger simulation."""
        steps_done: list[str] = []
        try:
            pose_csv_win = self._to_windows_unc_path(Path(record["pose_csv"]))
            self.ui_queue.put(("log", f"  [1/4] pose.csv 확인 완료\n"))
            steps_done.append("export")

            # Step 2: start outer move service
            if existing_service_pid is not None:
                service_result = {"pid": existing_service_pid}
                steps_done.append("service_reused")
                self.ui_queue.put(("log", f"  [2/4] 기존 서비스 재사용 (PID {existing_service_pid})\n"))
            else:
                launcher_script = self._to_windows_unc_path(SCRIPTS_DIR / "start_mechviz_service.ps1")
                service_script = self._to_windows_unc_path(SCRIPTS_DIR / "viz_outer_move_service.py")
                self.ui_queue.put(("log", "  [2/4] 서비스 시작 요청 중...\n"))
                service_result = start_outer_move_service(
                    windows_launcher_script=launcher_script,
                    windows_service_script=service_script,
                    windows_pose_csv_path=pose_csv_win,
                    config=self.mechviz_config,
                )
                steps_done.append("service")
                self.ui_queue.put(("log", f"  [2/4] 서비스 시작 완료 (PID {service_result['pid']})\n"))

            # Step 3: open Mech-Viz project
            project_dir = str(self.mechviz_config.get("project_dir", "")).strip()
            open_target = project_dir
            if project_dir:
                wsl_project_dir = self._to_wsl_path_from_windows(project_dir)
                viz_candidates = sorted(wsl_project_dir.glob("*.viz"))
                if viz_candidates:
                    open_target = self._to_windows_unc_path(viz_candidates[0])
            if open_target:
                open_mechviz_project(open_target)
                steps_done.append("project_open")
                self.ui_queue.put(("log", f"  [3/4] 프로젝트 열기 완료\n"))
            else:
                self.ui_queue.put(("log", f"  [3/4] 프로젝트 경로 미설정 (건너뜀)\n"))

            # Step 4: attempt simulation trigger
            trigger_result = trigger_mechviz_execution(self.mechviz_config)
            if trigger_result["triggered"]:
                steps_done.append("trigger")
                self.ui_queue.put(("log", f"  [4/4] 시뮬레이션 트리거 성공\n"))
            else:
                self.ui_queue.put((
                    "log",
                    f"  [4/4] 시뮬레이션 자동 트리거 실패 ({trigger_result['reason']})"
                    " — Mech-Viz에서 수동으로 실행해 주세요\n",
                ))

            self.ui_queue.put((
                "mechviz_simulate_done",
                {
                    "seam": record["name"],
                    "steps_done": steps_done,
                    "service_pid": service_result["pid"],
                    "trigger_result": trigger_result,
                    **exported,
                },
            ))
        except Exception:
            self.ui_queue.put(("mechviz_simulate_error", traceback.format_exc()))

    def _mechviz_project_open_worker(self) -> None:
        try:
            project_dir = str(self.mechviz_config.get("project_dir", "")).strip()
            if not project_dir:
                raise RuntimeError("mechviz_runtime_config.json에 project_dir가 비어 있습니다.")

            wsl_project_dir = self._to_wsl_path_from_windows(project_dir)
            target = project_dir
            viz_candidates = sorted(wsl_project_dir.glob("*.viz"))
            if viz_candidates:
                target = self._to_windows_unc_path(viz_candidates[0])

            result = open_mechviz_project(target)
            self.ui_queue.put(("mechviz_project_opened", result))
        except Exception:
            self.ui_queue.put(("mechviz_project_error", traceback.format_exc()))

    def _dts_e2e_worker(self, record: dict[str, Any]) -> None:
        try:
            script_path = self._to_windows_unc_path(SCRIPTS_DIR / "run_dts_full_auto_e2e.cmd")
            payload_path = self._to_windows_unc_path(Path(record["txt_1100"]))
            proc = subprocess.run(
                [
                    "cmd.exe",
                    "/c",
                    script_path,
                    "-GapMode",
                    "ok",
                    "-PayloadFile",
                    payload_path,
                ],
                capture_output=True,
            )
            stdout = proc.stdout.decode("utf-8", errors="replace") if proc.stdout else ""
            stderr = proc.stderr.decode("utf-8", errors="replace") if proc.stderr else ""
            combined = stdout + ("\n" + stderr if stderr else "")
            parsed = parse_dts_e2e_output(combined)
            self.ui_queue.put(
                (
                    "dts_e2e_done",
                    {
                        "seam": record["name"],
                        "payload_file": record["txt_1100"],
                        "returncode": proc.returncode,
                        "parsed": parsed,
                        "raw_output": combined,
                    },
                )
            )
        except Exception:
            self.ui_queue.put(("dts_e2e_error", traceback.format_exc()))

    def _start_run(self) -> None:
        if self.run_thread and self.run_thread.is_alive():
            self._show_error("이미 경로 생성이 실행 중입니다.")
            return
        if not self._ensure_idle():
            return

        validated = self._validate_run_request()
        if validated is None:
            return
        capture_id, capture_entry, seams, step_mm = validated

        self.status_var.set("실행 중...")
        self.review_var.set("검토안 미선택")
        self.baseline_summary = None
        self.corrected_summary = None
        self.current_summary = None
        self.log_text.delete("1.0", tk.END)
        for item in self.result_tree.get_children():
            self.result_tree.delete(item)
        self._reset_overlay_compare(
            left_text="경로 생성 실행 중...",
            right_text="보정 비교를 실행하면 원본/보정안을 나란히 표시합니다",
        )
        self.output_dir_var.set("-")

        self.run_thread = threading.Thread(
            target=self._run_pipeline_worker,
            args=(capture_id, capture_entry, seams, step_mm, self.edge_snap_var.get()),
            daemon=True,
        )
        self.run_thread.start()
        self._refresh_action_state()

    def _start_correction_preview(self) -> None:
        if self.correction_thread and self.correction_thread.is_alive():
            self._show_error("보정 미리보기가 이미 실행 중입니다.")
            return
        if not self._ensure_idle():
            return
        validated = self._validate_run_request()
        if validated is None:
            return
        capture_id, capture_entry, seams, step_mm = validated

        self.status_var.set("보정 비교 생성 중...")
        self.review_var.set("원본/보정안 비교 생성 중")
        self.log_text.delete("1.0", tk.END)
        for item in self.result_tree.get_children():
            self.result_tree.delete(item)
        self._reset_overlay_compare(
            left_text="원본 경로 생성 중...",
            right_text="보정안 생성 중...",
        )
        self.output_dir_var.set("-")

        self.correction_thread = threading.Thread(
            target=self._correction_preview_worker,
            args=(capture_id, capture_entry, seams, step_mm),
            daemon=True,
        )
        self.correction_thread.start()
        self._refresh_action_state()

    def _start_snap_policy_preview(self) -> None:
        if self.correction_thread and self.correction_thread.is_alive():
            self._show_error("다른 비교 작업이 이미 실행 중입니다.")
            return
        if not self._ensure_idle():
            return
        validated = self._validate_run_request()
        if validated is None:
            return
        capture_id, capture_entry, seams, step_mm = validated

        self.status_var.set("Snap 정책 비교 생성 중...")
        self.review_var.set("현재 정책/대안 정책 비교 생성 중")
        self.log_text.delete("1.0", tk.END)
        for item in self.result_tree.get_children():
            self.result_tree.delete(item)
        self._reset_overlay_compare(
            left_text="현재 정책 경로 생성 중...",
            right_text="대안 정책 경로 생성 중...",
        )
        self.output_dir_var.set("-")

        self.correction_thread = threading.Thread(
            target=self._snap_policy_preview_worker,
            args=(capture_id, capture_entry, seams, step_mm),
            daemon=True,
        )
        self.correction_thread.start()
        self._refresh_action_state()

    def _execute_pipeline_run(
        self,
        capture_id: str,
        capture_entry: dict[str, Any],
        seams: list[str],
        step_mm: float,
        edge_snap: bool,
        run_dir: Path,
        writer: QueueWriter,
        variant_label: str,
        compare_label: str | None = None,
        snap_mode_overrides: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        rgb_path = guess_rgb_path(Path(capture_entry["raw_capture_ply"]))
        writer.write(f"variant={variant_label}\n")
        if compare_label:
            writer.write(f"compare_label={compare_label}\n")
        writer.write(f"capture={capture_id}\n")
        writer.write(f"seams={', '.join(seams)}\n")
        writer.write(f"edge_snap={edge_snap}\n\n")

        ref_pcd = o3d.io.read_point_cloud(str(Path(self.registry["reference_pcd"])))
        eval_pcd = o3d.io.read_point_cloud(str(resolve_canonical_eval_pcd(capture_entry)))
        T_icp = np.load(capture_entry["icp_transform_npy"])

        results = []
        pose_csv_paths: list[Path] = []
        for seam_name in seams:
            seam_dir = run_dir / seam_name
            snap_mode = "auto"
            if snap_mode_overrides and seam_name in snap_mode_overrides:
                snap_mode = snap_mode_overrides[seam_name]
            result = process_seam(
                seam_name,
                SEAM_CANDIDATES[seam_name],
                ref_pcd,
                eval_pcd,
                T_icp,
                step_mm,
                seam_dir,
                edge_snap=edge_snap,
                snap_mode=snap_mode,
            )
            pose_csv_paths.append(seam_dir / f"{seam_name}_pose.csv")
            results.append(
                {
                    "name": seam_name,
                    "n_poses": result["n_poses"],
                    "score": result["score"],
                    "pose_csv": str(seam_dir / f"{seam_name}_pose.csv"),
                    "txt_1100": str(seam_dir / f"{seam_name}_1100.txt"),
                }
            )

        overlay_path = None
        overlay_stats = {}
        overlay_warning = None
        if rgb_path and Path(capture_entry["raw_capture_ply"]).exists():
            overlay_path = run_dir / "overlay.png"
            try:
                overlay_path, overlay_stats = generate_overlay_image(
                    rgb_path=rgb_path,
                    raw_pcd_path=Path(capture_entry["raw_capture_ply"]),
                    pose_csv_paths=pose_csv_paths,
                    out_path=overlay_path,
                )
                writer.write(f"\noverlay={overlay_path}\n")
            except Exception as exc:
                overlay_path = None
                overlay_stats = {}
                overlay_warning = f"{type(exc).__name__}: {exc}"
                writer.write(f"\n[overlay] WARNING: {overlay_warning}\n")
        else:
            writer.write("\nRGB와 organized raw PLY 쌍을 찾지 못해 오버레이를 건너뜁니다.\n")

        summary = {
            "capture_id": capture_id,
            "run_dir": str(run_dir),
            "variant": variant_label,
            "variant_label": variant_label,
            "compare_label": compare_label or variant_label,
            "edge_snap": edge_snap,
            "step_mm": step_mm,
            "snap_mode_overrides": snap_mode_overrides or {},
            "results": results,
            "overlay_path": str(overlay_path) if overlay_path else None,
            "overlay_stats": overlay_stats,
            "overlay_warning": overlay_warning,
            "raw_capture_ply": capture_entry["raw_capture_ply"],
            "rgb_path": str(rgb_path) if rgb_path else None,
        }
        run_dir.mkdir(parents=True, exist_ok=True)
        with (run_dir / "summary.json").open("w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        return summary

    def _run_pipeline_worker(
        self,
        capture_id: str,
        capture_entry: dict[str, Any],
        seams: list[str],
        step_mm: float,
        edge_snap: bool,
    ) -> None:
        writer = QueueWriter(self.ui_queue)
        run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = GUI_RUNS_DIR / f"{run_stamp}_{capture_id}"

        try:
            with contextlib.redirect_stdout(writer):
                summary = self._execute_pipeline_run(
                    capture_id=capture_id,
                    capture_entry=capture_entry,
                    seams=seams,
                    step_mm=step_mm,
                    edge_snap=edge_snap,
                    run_dir=run_dir,
                    writer=writer,
                    variant_label="corrected" if edge_snap else "baseline",
                )

            self.ui_queue.put(("done", summary))
        except Exception:
            self.ui_queue.put(("error", traceback.format_exc()))

    def _correction_preview_worker(
        self,
        capture_id: str,
        capture_entry: dict[str, Any],
        seams: list[str],
        step_mm: float,
    ) -> None:
        writer = QueueWriter(self.ui_queue)
        run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        preview_root = GUI_RUNS_DIR / f"{run_stamp}_{capture_id}_correction_preview"
        try:
            with contextlib.redirect_stdout(writer):
                baseline_summary = self._execute_pipeline_run(
                    capture_id=capture_id,
                    capture_entry=capture_entry,
                    seams=seams,
                    step_mm=step_mm,
                    edge_snap=False,
                    run_dir=preview_root / "original",
                    writer=writer,
                    variant_label="baseline",
                    compare_label="원본",
                )
                writer.write("\n" + "=" * 60 + "\n")
                corrected_summary = self._execute_pipeline_run(
                    capture_id=capture_id,
                    capture_entry=capture_entry,
                    seams=seams,
                    step_mm=step_mm,
                    edge_snap=True,
                    run_dir=preview_root / "corrected",
                    writer=writer,
                    variant_label="corrected",
                    compare_label="보정안",
                )
                comparison = {
                    "capture_id": capture_id,
                    "preview_root": str(preview_root),
                    "baseline_metrics": summarize_run_summary(baseline_summary),
                    "corrected_metrics": summarize_run_summary(corrected_summary),
                    "recommended_variant": recommended_variant_name(
                        baseline_summary,
                        corrected_summary,
                    ),
                }
                preview_root.mkdir(parents=True, exist_ok=True)
                with (preview_root / "correction_compare.json").open("w", encoding="utf-8") as f:
                    json.dump(comparison, f, indent=2)
            self.ui_queue.put(
                (
                    "correction_done",
                    {
                        "baseline": baseline_summary,
                        "corrected": corrected_summary,
                        "comparison": comparison,
                    },
                )
            )
        except Exception:
            self.ui_queue.put(("error", traceback.format_exc()))

    def _snap_policy_preview_worker(
        self,
        capture_id: str,
        capture_entry: dict[str, Any],
        seams: list[str],
        step_mm: float,
    ) -> None:
        writer = QueueWriter(self.ui_queue)
        run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        preview_root = GUI_RUNS_DIR / f"{run_stamp}_{capture_id}_snap_preview"
        try:
            alt_overrides: dict[str, str] = {}
            for seam_name in seams:
                strategy = (
                    SEAM_CANDIDATES[seam_name]
                    .get("runtime_contract", {})
                    .get("snap_strategy", "ref_pcd_surface_snap_k5")
                )
                if strategy == "ref_pcd_no_snap":
                    alt_overrides[seam_name] = "constrained_k5"
                else:
                    alt_overrides[seam_name] = "no_snap"

            with contextlib.redirect_stdout(writer):
                baseline_summary = self._execute_pipeline_run(
                    capture_id=capture_id,
                    capture_entry=capture_entry,
                    seams=seams,
                    step_mm=step_mm,
                    edge_snap=False,
                    run_dir=preview_root / "current_policy",
                    writer=writer,
                    variant_label="policy_current",
                    compare_label="현재 정책",
                )
                writer.write("\n" + "=" * 60 + "\n")
                alternative_summary = self._execute_pipeline_run(
                    capture_id=capture_id,
                    capture_entry=capture_entry,
                    seams=seams,
                    step_mm=step_mm,
                    edge_snap=False,
                    run_dir=preview_root / "alternative_policy",
                    writer=writer,
                    variant_label="policy_alternative",
                    compare_label="대안 정책",
                    snap_mode_overrides=alt_overrides,
                )
                comparison = {
                    "capture_id": capture_id,
                    "preview_root": str(preview_root),
                    "baseline_metrics": summarize_run_summary(baseline_summary),
                    "corrected_metrics": summarize_run_summary(alternative_summary),
                    "recommended_variant": recommended_variant_name(
                        baseline_summary,
                        alternative_summary,
                    ),
                    "alternative_policy": alt_overrides,
                }
                preview_root.mkdir(parents=True, exist_ok=True)
                with (preview_root / "snap_policy_compare.json").open("w", encoding="utf-8") as f:
                    json.dump(comparison, f, indent=2)
            self.ui_queue.put(
                (
                    "correction_done",
                    {
                        "baseline": baseline_summary,
                        "corrected": alternative_summary,
                        "comparison": comparison,
                    },
                )
            )
        except Exception:
            self.ui_queue.put(("error", traceback.format_exc()))

    def _poll_queue(self) -> None:
        try:
            self._poll_queue_inner()
        except Exception:
            # Log the crash so the user can see it, but never let polling die.
            try:
                self.log_text.insert(tk.END, f"[poll error] {traceback.format_exc()}")
                self.log_text.see(tk.END)
            except Exception:
                pass
        finally:
            # Always clear dead threads and re-schedule, even after errors.
            self._clear_dead_threads()
            self._refresh_action_state()
            self.root.after(100, self._poll_queue)

    def _clear_dead_threads(self) -> None:
        """Set thread refs to None when the thread has finished."""
        for attr in (
            "camera_thread", "icp_thread", "run_thread", "correction_thread",
            "export_thread", "e2e_thread", "mechviz_service_thread",
            "mechviz_open_thread", "mechviz_simulate_thread",
        ):
            t = getattr(self, attr, None)
            if t is not None and not t.is_alive():
                setattr(self, attr, None)

    def _poll_queue_inner(self) -> None:
        while True:
            try:
                kind, payload = self.ui_queue.get_nowait()
            except queue.Empty:
                break

            if kind == "log":
                self.log_text.insert(tk.END, payload)
                self.log_text.see(tk.END)
            elif kind == "done":
                self._handle_run_complete(payload)
            elif kind == "camera_discovered":
                self._handle_camera_discovered(payload)
            elif kind == "camera_capture_done":
                self._handle_camera_capture_done(payload)
            elif kind == "icp_registered":
                self._handle_icp_registered(payload)
            elif kind == "correction_done":
                self._handle_correction_done(payload)
            elif kind == "mechviz_exported":
                self._handle_mechviz_exported(payload)
            elif kind == "mechviz_service_started":
                self._handle_mechviz_service_started(payload)
            elif kind == "mechviz_service_stopped":
                self._handle_mechviz_service_stopped(payload)
            elif kind == "mechviz_project_opened":
                self._handle_mechviz_project_opened(payload)
            elif kind == "mechviz_simulate_done":
                self._handle_mechviz_simulate_done(payload)
            elif kind == "dts_e2e_done":
                self._handle_dts_e2e_done(payload)
            elif kind == "camera_error":
                self.camera_status_var.set("카메라 작업 실패")
                self.log_text.insert(tk.END, payload)
                self.log_text.see(tk.END)
                self._show_error("카메라 작업이 실패했습니다. 로그를 확인해 주세요.")
            elif kind == "icp_error":
                self.status_var.set("ICP 등록 실패")
                self.log_text.insert(tk.END, payload)
                self.log_text.see(tk.END)
                self._show_error("ICP 등록이 실패했습니다. 로그를 확인해 주세요.")
            elif kind == "mechviz_export_error":
                self.status_var.set("Mech-Viz 내보내기 실패")
                self.log_text.insert(tk.END, payload)
                self.log_text.see(tk.END)
                self._show_error("Mech-Viz 내보내기가 실패했습니다. 로그를 확인해 주세요.")
            elif kind == "mechviz_service_error":
                self.status_var.set("Mech-Viz 서비스 실패")
                self.log_text.insert(tk.END, payload)
                self.log_text.see(tk.END)
                self._show_error("Mech-Viz 서비스 작업이 실패했습니다. 로그를 확인해 주세요.")
            elif kind == "mechviz_project_error":
                self.status_var.set("Mech-Viz 프로젝트 열기 실패")
                self.log_text.insert(tk.END, payload)
                self.log_text.see(tk.END)
                self._show_error("Mech-Viz 프로젝트 열기가 실패했습니다. 로그를 확인해 주세요.")
            elif kind == "mechviz_simulate_error":
                self.status_var.set("Mech-Viz 시뮬레이션 실패")
                self.log_text.insert(tk.END, payload)
                self.log_text.see(tk.END)
                self._show_error("Mech-Viz 시뮬레이션이 실패했습니다. 로그를 확인해 주세요.")
            elif kind == "dts_e2e_error":
                self.status_var.set("DTS 자동 검증 실패")
                self.log_text.insert(tk.END, payload)
                self.log_text.see(tk.END)
                self._show_error("DTS 자동 검증 실행이 실패했습니다. 로그를 확인해 주세요.")
            elif kind == "error":
                self.status_var.set("실행 실패")
                self.log_text.insert(tk.END, payload)
                self.log_text.see(tk.END)
                self._show_error("경로 생성 실행이 실패했습니다. 로그를 확인해 주세요.")

    def _apply_display_summary(self, summary: dict[str, Any], review_label: str | None = None) -> None:
        self.current_summary = summary
        self.output_dir_var.set(summary["run_dir"])

        for item in self.result_tree.get_children():
            self.result_tree.delete(item)

        for result in summary["results"]:
            score = result["score"]
            self.result_tree.insert(
                "",
                tk.END,
                values=(
                    result["name"],
                    result["n_poses"],
                    f"{score['mean_nn_mm']:.3f}",
                    f"{score['p90_nn_mm']:.3f}",
                    f"{score['max_nn_mm']:.3f}",
                    result["pose_csv"],
                    result["txt_1100"],
                ),
            )

        self._refresh_overlay_compare()

        if review_label is not None:
            self.review_var.set(review_label)

    def _handle_run_complete(self, summary: dict[str, Any]) -> None:
        variant = summary.get("variant", "baseline")
        self.status_var.set("실행 완료")
        # Clear thread ref so _active_task_name no longer blocks other actions.
        self.run_thread = None
        self.correction_thread = None
        self._apply_display_summary(
            summary,
            review_label=f"현재 표시: {'보정안' if variant == 'corrected' else '원본'}",
        )
        if variant == "baseline":
            self.baseline_summary = summary
        elif variant == "corrected":
            self.corrected_summary = summary
        self._refresh_action_state()

    def _handle_camera_discovered(self, cameras: list[dict[str, Any]]) -> None:
        self.camera_thread = None
        if not cameras:
            self.camera_status_var.set("검색된 카메라 없음")
            self.log_text.insert(tk.END, "camera_discover=count=0\n")
            self.log_text.see(tk.END)
            self._refresh_action_state()
            return

        first_ip = cameras[0].get("ip_address", "")
        if first_ip and not self.camera_ip_var.get().strip():
            self.camera_ip_var.set(first_ip)
        self.camera_status_var.set(f"카메라 {len(cameras)}대 검색됨")
        self.log_text.insert(tk.END, json.dumps({"camera_discovered": cameras}, indent=2) + "\n")
        self.log_text.see(tk.END)
        self._refresh_action_state()

    def _handle_camera_capture_done(self, result: dict[str, Any]) -> None:
        self.camera_thread = None
        raw_pcd = Path(result["raw_capture_ply"])
        capture_id = live_capture_id_from_raw_pcd(raw_pcd) or raw_pcd.stem
        if capture_id in self.capture_entries:
            capture_id = f"live:{capture_id}"

        self.camera_status_var.set("촬영 저장 완료 (ICP 등록 필요)")
        self.log_text.insert(tk.END, json.dumps({"camera_capture": result}, indent=2) + "\n")
        self.log_text.see(tk.END)
        self._refresh_capture_entries(select_capture_id=capture_id)
        self._refresh_action_state()

    def _handle_icp_registered(self, result: dict[str, Any]) -> None:
        self.icp_thread = None
        capture_id = result["capture_id"]
        self.status_var.set("ICP 등록 완료")
        self.log_text.insert(tk.END, json.dumps({"icp_registered": result}, indent=2) + "\n")
        self.log_text.see(tk.END)
        self._refresh_capture_entries(select_capture_id=capture_id)
        self._refresh_action_state()

    def _handle_correction_done(self, payload: dict[str, Any]) -> None:
        self.correction_thread = None
        self.baseline_summary = payload["baseline"]
        self.corrected_summary = payload["corrected"]
        comparison = payload["comparison"]
        recommended = comparison["recommended_variant"]
        baseline_label = _summary_label(self.baseline_summary, "원본")
        corrected_label = _summary_label(self.corrected_summary, "보정안")
        self.status_var.set("보정 비교 준비 완료")
        self.log_text.insert(tk.END, json.dumps({"correction_compare": comparison}, indent=2) + "\n")
        self.log_text.see(tk.END)
        to_show = self.corrected_summary if recommended == "corrected" else self.baseline_summary
        self._apply_display_summary(
            to_show,
            review_label=(
                f"비교 완료 · 권장안: {corrected_label}"
                if recommended == "corrected"
                else f"비교 완료 · 권장안: {baseline_label}"
            ),
        )
        self._refresh_action_state()

    def _apply_corrected(self) -> None:
        if self.corrected_summary is None:
            self._show_error("아직 적용할 보정안 미리보기가 없습니다.")
            return
        self.status_var.set("보정안 적용")
        self._apply_display_summary(
            self.corrected_summary,
            review_label=f"적용 상태: {_summary_label(self.corrected_summary, '보정안')}",
        )

    def _keep_original(self) -> None:
        if self.baseline_summary is None:
            self._show_error("아직 유지할 원본 미리보기가 없습니다.")
            return
        self.status_var.set("원본 유지")
        self._apply_display_summary(
            self.baseline_summary,
            review_label=f"적용 상태: {_summary_label(self.baseline_summary, '원본')}",
        )

    def _handle_mechviz_exported(self, payload: dict[str, Any]) -> None:
        self.export_thread = None
        self.status_var.set("Mech-Viz 내보내기 완료")
        self.log_text.insert(tk.END, json.dumps({"mechviz_exported": payload}, indent=2) + "\n")
        self.log_text.see(tk.END)
        self._refresh_action_state()

    def _handle_mechviz_service_started(self, payload: dict[str, Any]) -> None:
        self.mechviz_service_thread = None
        self.mechviz_service_pid = int(payload["pid"])
        self.mechviz_service_var.set(f"서비스 실행 중 · PID {payload['pid']}")
        self.status_var.set("Mech-Viz 서비스 실행 중")
        self.log_text.insert(tk.END, json.dumps({"mechviz_service_started": payload}, indent=2) + "\n")
        self.log_text.see(tk.END)
        self._refresh_action_state()

    def _handle_mechviz_service_stopped(self, payload: dict[str, Any]) -> None:
        self.mechviz_service_thread = None
        stopped = bool(payload.get("stopped"))
        if stopped:
            self.mechviz_service_var.set("서비스 중지")
            self.status_var.set("Mech-Viz 서비스 중지")
            self.mechviz_service_pid = None
        else:
            self.mechviz_service_var.set(f"서비스 상태 불확실 · PID {payload['pid']}")
            self.status_var.set("Mech-Viz 서비스 중지 실패")
        self.log_text.insert(tk.END, json.dumps({"mechviz_service_stopped": payload}, indent=2) + "\n")
        self.log_text.see(tk.END)
        self._refresh_action_state()

    def _handle_mechviz_project_opened(self, payload: dict[str, Any]) -> None:
        self.mechviz_open_thread = None
        self.status_var.set("Mech-Viz 프로젝트 열기 완료")
        self.log_text.insert(tk.END, json.dumps({"mechviz_project_opened": payload}, indent=2) + "\n")
        self.log_text.see(tk.END)
        self._refresh_action_state()

    def _handle_mechviz_simulate_done(self, payload: dict[str, Any]) -> None:
        service_pid = payload.get("service_pid")
        if service_pid is not None:
            self.mechviz_service_pid = int(service_pid)
            self.mechviz_service_var.set(f"서비스 실행 중 · PID {service_pid}")

        trigger_result = payload.get("trigger_result", {})
        triggered = trigger_result.get("triggered", False)
        steps = payload.get("steps_done", [])

        if triggered:
            self.status_var.set("Mech-Viz 시뮬레이션 실행 중")
        elif "service" in steps:
            self.status_var.set("서비스 준비 완료 · Mech-Viz에서 수동 실행 필요")
        else:
            self.status_var.set("Mech-Viz 시뮬레이션 부분 완료")

        self.log_text.insert(tk.END, json.dumps({"mechviz_simulate_done": payload}, indent=2) + "\n")
        self.log_text.see(tk.END)
        self.mechviz_simulate_thread = None
        self._refresh_action_state()

    def _handle_dts_e2e_done(self, payload: dict[str, Any]) -> None:
        parsed = payload["parsed"]
        verdict_info = finalize_dts_e2e_verdict(parsed, int(payload["returncode"]))
        verdict = verdict_info["verdict"]
        verdict_ko = "PASS" if verdict == "PASS" else "FAIL" if verdict == "FAIL" else verdict
        self.status_var.set(f"DTS 자동 검증 {verdict_ko}")

        # Structured summary instead of raw JSON dump
        lines = [
            f"{'=' * 50}",
            f"  DTS 자동 검증 결과",
            f"{'=' * 50}",
            f"  Seam:       {payload['seam']}",
            f"  판정:       {verdict_ko}",
            f"  Gap 모드:   {parsed.get('gap_mode') or '-'}",
            f"  OK 로그:    {'기록됨' if parsed.get('ok_log_grew') else '변화 없음'}",
            f"  NG 로그:    {'기록됨' if parsed.get('ng_log_grew') else '변화 없음'}",
            f"  종료 코드:  {payload['returncode']}",
            f"  판정 근거:  {verdict_info.get('reason', '-')}",
            f"  Payload:    {payload['payload_file']}",
        ]
        log_dir = parsed.get("log_dir")
        if log_dir:
            lines.append(f"  로그 폴더:  {log_dir}")
        lines.append(f"{'=' * 50}")

        # Append structured log sections if present
        sections = parsed.get("sections", {})
        section_labels = {
            "robot.out": "Robot 출력",
            "robot.err": "Robot 오류",
            "vision.out": "Vision 출력",
            "vision.err": "Vision 오류",
            "ok.log tail": "OK 로그 (최근)",
            "ng.log tail": "NG 로그 (최근)",
        }
        for section_key, label in section_labels.items():
            body = sections.get(section_key)
            if not body:
                continue
            lines.append(f"\n--- {label} ---")
            # Limit to last 10 lines per section
            section_lines = body.splitlines()
            if len(section_lines) > 10:
                lines.append(f"  ... ({len(section_lines) - 10}줄 생략)")
                section_lines = section_lines[-10:]
            for sl in section_lines:
                lines.append(f"  {sl}")

        # Show any other unknown sections
        for section_key, body in sections.items():
            if section_key in section_labels:
                continue
            lines.append(f"\n--- {section_key} ---")
            for sl in body.splitlines()[-10:]:
                lines.append(f"  {sl}")

        # Show raw output when FAIL or no sections parsed (helps debugging)
        raw_output = payload.get("raw_output", "")
        if verdict != "PASS" and not sections and raw_output.strip():
            lines.append(f"\n--- Raw Output ---")
            for rl in raw_output.strip().splitlines()[-30:]:
                lines.append(f"  {rl}")

        lines.append("")
        self.log_text.insert(tk.END, "\n".join(lines) + "\n")
        self.log_text.see(tk.END)
        self.e2e_thread = None
        self._refresh_action_state()

    def _show_error(self, message: str) -> None:
        if messagebox is not None:
            messagebox.showerror("배터리 케이스 GUI", message)
        else:
            self.log_text.insert(tk.END, f"ERROR: {message}\n")
            self.log_text.see(tk.END)


def main() -> None:
    if tk is None or ttk is None:
        sys.exit(
            "현재 Python 환경에는 tkinter가 없습니다. "
            "tkinter가 설치된 호스트 Python에서 이 GUI를 실행해 주세요."
        )

    root = tk.Tk()
    app = BatteryCaseGuiApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
