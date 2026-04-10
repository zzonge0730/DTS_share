#!/usr/bin/env python3
"""
mecheye_capture.py - WSL-first Mech-Eye area-scan capture wrapper.

This module intentionally focuses on:
- loading/saving a small camera config
- optional camera discovery
- direct-IP or first-discovered camera connection
- saving RGB / depth / textured PLY into the existing captures directory

It does not compute ICP transforms. New captures remain "pending ICP" until
they are registered into the battery-case pipeline.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import open3d as o3d
from PIL import Image


import _bootstrap  # noqa: F401 — repo root + scripts/ on sys.path

from dts.config import (
    REPO_ROOT,
    DEFAULT_CAMERA_CONFIG,
    get_captures_dir,
)

try:
    from mecheye.area_scan_3d_camera import (
        Camera,
        CameraInfo,
        ColorTypeOf2DCamera_Color,
        ColorTypeOf2DCamera_Monochrome,
        Frame2DAnd3D,
    )
    from mecheye.shared import FileFormat_PLY

    SDK_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - depends on host SDK install
    Camera = None
    CameraInfo = None
    Frame2DAnd3D = None
    FileFormat_PLY = None
    ColorTypeOf2DCamera_Color = None
    ColorTypeOf2DCamera_Monochrome = None
    SDK_IMPORT_ERROR = exc


def default_camera_config() -> dict[str, Any]:
    return {
        "camera_ip": "",
        "captures_dir": str(get_captures_dir()),
        "default_capture_tag": "gui",
        "save_rgb": True,
        "save_depth": True,
        "save_textured_point_cloud": True,
    }


def load_camera_config(path: Path = DEFAULT_CAMERA_CONFIG) -> dict[str, Any]:
    config = default_camera_config()
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            loaded = json.load(f)
        config.update(loaded)
    return config


def save_camera_config(config: dict[str, Any], path: Path = DEFAULT_CAMERA_CONFIG) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    return path


def sdk_available() -> bool:
    return Camera is not None and SDK_IMPORT_ERROR is None


def sdk_status_text() -> str:
    if sdk_available():
        return "SDK ready"
    assert SDK_IMPORT_ERROR is not None
    return f"SDK unavailable: {type(SDK_IMPORT_ERROR).__name__}: {SDK_IMPORT_ERROR}"


def _ensure_sdk() -> None:
    if not sdk_available():
        raise RuntimeError(sdk_status_text())


def _sanitize_tag(tag: str | None) -> str:
    if not tag:
        return "gui"
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", tag.strip())
    return cleaned or "gui"


def _status_text(status: Any) -> str:
    parts: list[str] = []
    for name in ("code", "description", "message"):
        try:
            value = getattr(status, name)
            if callable(value):
                value = value()
            if value not in (None, ""):
                parts.append(f"{name}={value}")
        except Exception:
            continue
    if parts:
        return ", ".join(parts)
    return str(status)


def _require_ok(status: Any, action: str) -> None:
    if hasattr(status, "is_ok") and status.is_ok():
        return
    raise RuntimeError(f"{action} failed: {_status_text(status)}")


def _camera_info_to_dict(camera_info: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in (
        "ip_address",
        "serial_number",
        "model",
        "name",
        "hardware_version",
        "firmware_version",
    ):
        try:
            value = getattr(camera_info, name)
            if callable(value):
                value = value()
            if value not in (None, ""):
                result[name] = str(value) if not isinstance(value, (str, int, float, bool)) else value
        except Exception:
            continue
    return result


def discover_cameras() -> list[dict[str, Any]]:
    _ensure_sdk()
    infos = Camera.discover_cameras()
    return [_camera_info_to_dict(info) for info in infos]


def _connect_camera(camera_ip: str | None) -> tuple[Any, dict[str, Any]]:
    _ensure_sdk()

    camera = Camera()
    if camera_ip and camera_ip.strip():
        _require_ok(camera.connect(camera_ip.strip()), f"connect({camera_ip.strip()})")
    else:
        discovered = Camera.discover_cameras()
        if not discovered:
            raise RuntimeError("No cameras discovered and no fixed IP configured.")
        _require_ok(camera.connect(discovered[0]), "connect(discovered[0])")

    camera_info = {}
    try:
        info = CameraInfo()
        _require_ok(camera.get_camera_info(info), "get_camera_info")
        camera_info = _camera_info_to_dict(info)
    except Exception:
        camera_info = {}

    return camera, camera_info


def _status_ok(status: Any) -> bool:
    return bool(hasattr(status, "is_ok") and status.is_ok())


def dump_current_user_set_parameters(
    camera_ip: str | None = None,
    output_path: Path | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = dict(default_camera_config() if config is None else config)
    camera = None
    try:
        camera, camera_info = _connect_camera(camera_ip or config.get("camera_ip"))
        user_set = camera.user_set_manager().current_user_set()

        current_user_set_name = None
        try:
            status, user_set_name = user_set.get_name()
            if _status_ok(status):
                current_user_set_name = user_set_name
        except Exception:
            current_user_set_name = None

        wanted = {
            "ProjectorPowerLevel",
            "ProjectorFringeCodingMode",
            "ProjectorAntiFlickerMode",
            "Scanning3DExposureSequence",
            "Scanning3DGain",
            "Scanning2DExposureMode",
            "Scanning2DHDRExposureSequence",
            "Scanning2DExposureTime",
            "Scanning2DGain",
        }
        values: dict[str, Any] = {}
        try:
            status, names = user_set.get_available_parameter_names()
            if not _status_ok(status):
                names = []
        except Exception:
            names = []

        for param_name in names:
            if param_name not in wanted:
                continue
            value: Any = None
            for reader_name in (
                "get_enum_value_string",
                "get_float_array_value",
                "get_float_value",
                "get_int_value",
                "get_bool_value",
            ):
                reader = getattr(user_set, reader_name, None)
                if reader is None:
                    continue
                try:
                    result = reader(param_name)
                except Exception:
                    continue
                if not isinstance(result, tuple) or not result:
                    continue
                status = result[0]
                if not _status_ok(status):
                    continue
                value = result[1] if len(result) == 2 else list(result[1:])
                break
            values[param_name] = value

        out = {
            "camera_info": camera_info,
            "current_user_set": current_user_set_name,
            "parameters": values,
        }
        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
        return out
    finally:
        if camera is not None:
            try:
                camera.disconnect()
            except Exception:
                pass


def _save_rgb_image(frame_2d: Any, rgb_path: Path) -> None:
    color_type = frame_2d.color_type()
    if color_type == ColorTypeOf2DCamera_Monochrome:
        image = np.asarray(frame_2d.get_gray_scale_image().data())
        Image.fromarray(image).save(rgb_path)
        return

    if color_type == ColorTypeOf2DCamera_Color:
        image = np.asarray(frame_2d.get_color_image().data())
        if image.ndim == 3 and image.shape[2] == 3:
            # Sample code saves via cv2; convert BGR -> RGB for Pillow.
            image = image[:, :, ::-1]
        Image.fromarray(image).save(rgb_path)
        return

    raise RuntimeError(f"Unsupported 2D image color type: {color_type}")


def _save_organized_point_cloud(
    frame_2d: Any, frame_3d: Any, pcd_path: Path,
) -> bool:
    """Save organized PLY with all W*H points (NaN for invalid).

    This preserves the 1:1 mapping between linear point index and image pixel,
    which is required by the overlay projection logic.
    Returns True on success, False on failure (caller should fall back to SDK save).
    """
    try:
        pc = frame_3d.get_untextured_point_cloud()
        w, h = pc.width(), pc.height()
        if w == 0 or h == 0:
            return False

        pts = np.asarray(pc.data(), dtype=np.float64).reshape(h * w, 3)

        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(pts)

        # Attach colors if available.
        try:
            color_type = frame_2d.color_type()
            if color_type == ColorTypeOf2DCamera_Color:
                colors = np.asarray(frame_2d.get_color_image().data())
                if colors.ndim == 3 and colors.shape[2] == 3:
                    colors = colors[:, :, ::-1]  # BGR -> RGB
                colors = colors.reshape(-1, 3).astype(np.float64) / 255.0
                if len(colors) == len(pts):
                    pcd.colors = o3d.utility.Vector3dVector(colors)
            elif color_type == ColorTypeOf2DCamera_Monochrome:
                gray = np.asarray(frame_2d.get_gray_scale_image().data()).ravel()
                if len(gray) == len(pts):
                    gray_f = gray.astype(np.float64) / 255.0
                    pcd.colors = o3d.utility.Vector3dVector(
                        np.column_stack([gray_f, gray_f, gray_f])
                    )
        except Exception:
            pass  # color is optional; organized geometry is what matters

        pcd_path.parent.mkdir(parents=True, exist_ok=True)
        o3d.io.write_point_cloud(str(pcd_path), pcd, write_ascii=False)
        return True
    except Exception:
        return False


def _save_depth_map(frame_3d: Any, depth_path: Path) -> None:
    depth = np.asarray(frame_3d.get_depth_map().data(), dtype=np.float32)
    Image.fromarray(depth).save(depth_path)


def capture_bundle(
    camera_ip: str | None = None,
    output_dir: Path | None = None,
    tag: str | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = dict(default_camera_config() if config is None else config)
    output_dir = Path(output_dir or config.get("captures_dir") or get_captures_dir())
    output_dir.mkdir(parents=True, exist_ok=True)

    capture_tag = _sanitize_tag(tag or config.get("default_capture_tag"))
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = f"{timestamp}_{capture_tag}"

    rgb_path = output_dir / f"rgb_image_{suffix}.png"
    depth_path = output_dir / f"depth_image_{suffix}.tiff"
    pcd_path = output_dir / f"point_cloud_{suffix}.ply"
    meta_path = output_dir / f"capture_meta_{suffix}.json"

    camera = None
    camera_info: dict[str, Any] = {}
    try:
        camera, camera_info = _connect_camera(camera_ip or config.get("camera_ip"))
        frame_all = Frame2DAnd3D()
        _require_ok(camera.capture_2d_and_3d(frame_all), "capture_2d_and_3d")

        if config.get("save_rgb", True):
            _save_rgb_image(frame_all.frame_2d(), rgb_path)
        if config.get("save_depth", True):
            _save_depth_map(frame_all.frame_3d(), depth_path)
        if config.get("save_textured_point_cloud", True):
            # Prefer organized PLY (W*H points including NaN) so overlay
            # pixel mapping works.  Fall back to SDK save if it fails.
            if not _save_organized_point_cloud(
                frame_all.frame_2d(), frame_all.frame_3d(), pcd_path,
            ):
                _require_ok(
                    frame_all.save_textured_point_cloud(FileFormat_PLY, str(pcd_path)),
                    f"save_textured_point_cloud({pcd_path.name})",
                )

        meta = {
            "timestamp": timestamp,
            "tag": capture_tag,
            "camera_ip_requested": camera_ip or config.get("camera_ip", ""),
            "camera_info": camera_info,
            "rgb_path": str(rgb_path) if rgb_path.exists() else None,
            "depth_path": str(depth_path) if depth_path.exists() else None,
            "raw_capture_ply": str(pcd_path) if pcd_path.exists() else None,
            "status": "pending_icp_registration",
        }
        with meta_path.open("w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
        meta["meta_path"] = str(meta_path)
        return meta
    finally:
        if camera is not None:
            try:
                camera.disconnect()
            except Exception:
                pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Mech-Eye WSL capture helper")
    parser.add_argument("--config", type=Path, default=DEFAULT_CAMERA_CONFIG)
    parser.add_argument("--camera-ip", default=None, help="Fixed camera IP; blank falls back to discovery")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--tag", default=None)
    parser.add_argument("--discover", action="store_true", help="List discovered cameras and exit")
    parser.add_argument("--capture", action="store_true", help="Capture RGB/depth/PLY and save bundle")
    parser.add_argument("--dump-settings", action="store_true", help="Read current user set and key parameter values")
    parser.add_argument("--settings-out", type=Path, default=None)
    args = parser.parse_args()

    config = load_camera_config(args.config)

    if args.discover:
        print(json.dumps({"sdk_status": sdk_status_text(), "cameras": discover_cameras()}, indent=2))
        return

    if args.dump_settings:
        result = dump_current_user_set_parameters(
            camera_ip=args.camera_ip,
            output_path=args.settings_out,
            config=config,
        )
        print(json.dumps(result, indent=2))
        return

    if args.capture:
        result = capture_bundle(
            camera_ip=args.camera_ip,
            output_dir=args.output_dir,
            tag=args.tag,
            config=config,
        )
        print(json.dumps(result, indent=2))
        return

    parser.print_help()


if __name__ == "__main__":
    main()
