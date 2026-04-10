#!/usr/bin/env python3
r"""
viz_outer_move_service.py -- Register an OuterMoveService with Mech-Center hub
to feed pre-computed weld poses into Mech-Viz External Move step.

Reads a pose.csv (x_mm, y_mm, z_mm, rx_deg, ry_deg, rz_deg — Euler ZYX)
and internally converts to Mech-Viz world frame:
  1. mm → m
  2. Euler ZYX → quaternion
  3. Robot base offset (position only, orientation unchanged)
  4. Scalar-last → scalar-first for add_target()

Requirements:
  - Mech-Center (Communication Component) must be running
  - Run with the Mech-Mind bundled Python or ensure unified_service is on sys.path

Usage (Windows CMD):
    cd "C:\Mech-Mind\Mech-Vision & Mech-Viz-2.1.2\Communication Component"
    python\python.exe  path\to\viz_outer_move_service.py ^
        --pose-csv "path\to\U1_right_pose.csv" ^
        --robot-base 1.3 -0.5 0.0 ^
        --motion-type L --velocity 0.15

Then run the Mech-Viz simulation -- it will pull poses from this service.
Press Ctrl+C to stop.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import os
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup: add Mech-Mind SDK paths so unified_service and interface
# modules can be imported when running standalone.
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_CC_ROOT = None

# Auto-detect Communication Component root from common install locations
_CANDIDATES = [
    Path(r"C:\Mech-Mind\Mech-Vision & Mech-Viz-2.1.2\Communication Component"),
    Path(r"C:\Mech-Mind\Mech-Vision & Mech-Viz-2.2.0\Communication Component"),
]
for _c in _CANDIDATES:
    if (_c / "src" / "interface" / "services.py").exists():
        _CC_ROOT = _c
        break

if _CC_ROOT is None:
    # Allow override via environment variable
    _env = os.environ.get("MECH_CC_ROOT")
    if _env and Path(_env).exists():
        _CC_ROOT = Path(_env)

if _CC_ROOT is not None:
    # unified_service (gRPC stubs)
    _site = str(_CC_ROOT / "python" / "Lib" / "site-packages")
    if _site not in sys.path:
        sys.path.insert(0, _site)
    # interface.services, hub_service, etc.
    _src = str(_CC_ROOT / "src")
    if _src not in sys.path:
        sys.path.insert(0, _src)

_UNIFIED_SERVICE_IMPORT_ERROR = None
try:
    from unified_service.caller import HubCaller
    from unified_service.json_service import JsonService, start_server
except ImportError as e:
    _UNIFIED_SERVICE_IMPORT_ERROR = e

    class JsonService:  # type: ignore[override]
        """Fallback shim so pure logic can be unit-tested without Mech-Center."""

    HubCaller = None  # type: ignore[assignment]
    start_server = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Constants (mirrored from interface/services.py)
# ---------------------------------------------------------------------------
TCP_POSE = 1
MOVEJ = "J"
MOVEL = "L"

LOCAL_HUB_ADDRESS = "127.0.0.1:5308"

# Default robot base position in Mech-Viz world frame (meters)
DEFAULT_ROBOT_BASE = (1.3, -0.5, 0.0)


# ---------------------------------------------------------------------------
# Pose conversion: Euler ZYX (mm, deg) → world-frame scalar-first quaternion (m)
# ---------------------------------------------------------------------------
def _euler_zyx_to_quat(rx_deg: float, ry_deg: float, rz_deg: float):
    """Euler ZYX (extrinsic XYZ = intrinsic ZYX) → quaternion (qw, qx, qy, qz)."""
    rx = math.radians(rx_deg)
    ry = math.radians(ry_deg)
    rz = math.radians(rz_deg)

    cx, sx = math.cos(rx / 2), math.sin(rx / 2)
    cy, sy = math.cos(ry / 2), math.sin(ry / 2)
    cz, sz = math.cos(rz / 2), math.sin(rz / 2)

    # Intrinsic ZYX = extrinsic XYZ
    qw = cx * cy * cz + sx * sy * sz
    qx = sx * cy * cz - cx * sy * sz
    qy = cx * sy * cz + sx * cy * sz
    qz = cx * cy * sz - sx * sy * cz
    return qw, qx, qy, qz


def convert_pose_to_world(
    x_mm: float, y_mm: float, z_mm: float,
    rx_deg: float, ry_deg: float, rz_deg: float,
    robot_base: tuple[float, float, float],
) -> list[float]:
    """Convert one pose from pose.csv format to Mech-Viz world frame, scalar-first.

    Returns [x_m, y_m, z_m, qw, qx, qy, qz] ready for add_target().
    """
    # mm → m + robot base offset
    x_m = x_mm / 1000.0 + robot_base[0]
    y_m = y_mm / 1000.0 + robot_base[1]
    z_m = z_mm / 1000.0 + robot_base[2]

    # Euler → quaternion (already scalar-first)
    qw, qx, qy, qz = _euler_zyx_to_quat(rx_deg, ry_deg, rz_deg)

    return [x_m, y_m, z_m, qw, qx, qy, qz]


# ---------------------------------------------------------------------------
# CSV loading
# ---------------------------------------------------------------------------
def load_pose_csv(path: Path) -> list[list[float]]:
    """Load pose.csv: x_mm, y_mm, z_mm, rx_deg, ry_deg, rz_deg."""
    rows = []
    with path.open("r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)  # skip header
        for row in reader:
            if not row or not row[0].strip():
                continue
            rows.append([float(v) for v in row[:6]])
    return rows


def load_viz_csv(path: Path) -> list[list[float]]:
    """Load viz.csv: x_m, y_m, z_m, qx, qy, qz, qw (legacy support)."""
    poses = []
    with path.open("r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if not row or not row[0].strip():
                continue
            vals = [float(v) for v in row[:7]]
            poses.append(vals)
    return poses


# ---------------------------------------------------------------------------
# OuterMoveService
# ---------------------------------------------------------------------------
class WeldSeamOuterMoveService(JsonService):
    """Serves pre-computed weld poses to Mech-Viz External Move step.

    Poses are stored as [x_m, y_m, z_m, qw, qx, qy, qz] (scalar-first,
    world frame) — ready for add_target() with no further conversion.
    """

    service_type = "outer_move"
    service_name = "DTS Weld Seam Outer Move"

    def __init__(self, poses: list[list[float]],
                 velocity: float = 0.15,
                 acceleration: float = 0.15,
                 blend_radius: float = 0.01,
                 motion_type: str = MOVEL):
        self.targets: list[dict] = []
        self.poses = poses
        self.velocity = velocity
        self.acceleration = acceleration
        self.blend_radius = blend_radius
        self.motion_type = motion_type
        self.is_tcp_pose = True
        self.pick_or_place = 0
        self._call_count = 0
        self._pose_index = 0

    def gather_targets(self, di, jps, flange_pose):
        """Called by getMoveTargets — return ONE pose per call, advancing index.

        Mech-Viz flowchart uses a self-loop on the External Move step.
        waypointParametersList has 1 entry → exactly 1 target per call.
        The loop calls getMoveTargets() repeatedly until no targets remain.
        """
        self._call_count += 1
        if self._pose_index < len(self.poses):
            pose = self.poses[self._pose_index]
            self.add_target(TCP_POSE, pose)
            logging.info(
                "[gather_targets] call #%d, pose %d/%d: x=%.4f y=%.4f z=%.4f",
                self._call_count,
                self._pose_index + 1,
                len(self.poses),
                pose[0], pose[1], pose[2],
            )
            self._pose_index += 1
        else:
            logging.info(
                "[gather_targets] call #%d, all %d poses delivered",
                self._call_count,
                len(self.poses),
            )

    def add_target(self, move_target_type, target):
        self.targets.append({
            "move_target_type": move_target_type,
            "target": target,
        })

    def getMoveTargets(self, params, *_):
        di = params.get("di")
        jps = params.get("joint_positions")
        flange_pose = params.get("pose")
        logging.info(f"getMoveTargets: di={di}")

        self.gather_targets(di, jps, flange_pose)
        targets = self.targets[:]
        self.targets.clear()
        logging.info(f"Returning {len(targets)} targets")
        return {
            "targets": targets,
            "velocity": self.velocity,
            "acceleration": self.acceleration,
            "blend_radius": self.blend_radius,
            "motion_type": self.motion_type,
            "is_tcp_pose": self.is_tcp_pose,
            "pick_or_place": self.pick_or_place,
        }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    if _UNIFIED_SERVICE_IMPORT_ERROR is not None or HubCaller is None or start_server is None:
        sys.exit(
            f"Cannot import unified_service: {_UNIFIED_SERVICE_IMPORT_ERROR}\n"
            "Make sure Mech-Center's Python environment is on sys.path.\n"
            "Set MECH_CC_ROOT env var to Communication Component root if needed."
        )

    parser = argparse.ArgumentParser(
        description="Register OuterMoveService with Mech-Center hub for Mech-Viz External Move"
    )
    parser.add_argument("--pose-csv", type=Path, required=True,
                        help="Path to pose.csv (x_mm, y_mm, z_mm, rx_deg, ry_deg, rz_deg)")
    parser.add_argument("--robot-base", type=float, nargs=3,
                        default=list(DEFAULT_ROBOT_BASE),
                        metavar=("X", "Y", "Z"),
                        help=f"Robot base position in world frame (m). Default: {list(DEFAULT_ROBOT_BASE)}")
    parser.add_argument("--hub", default=LOCAL_HUB_ADDRESS,
                        help=f"Hub address (default: {LOCAL_HUB_ADDRESS})")
    parser.add_argument("--service-name", default="DTS Weld Seam Outer Move",
                        help="Service name registered with hub")
    parser.add_argument("--motion-type", choices=["L", "J"], default="L",
                        help="Motion type: L=MoveL (linear), J=MoveJ (joint). Default: L")
    parser.add_argument("--velocity", type=float, default=0.15,
                        help="Velocity ratio 0~1 (default: 0.15)")
    parser.add_argument("--acceleration", type=float, default=0.15,
                        help="Acceleration ratio 0~1 (default: 0.15)")
    parser.add_argument("--blend-radius", type=float, default=0.01,
                        help="Blend radius in meters (default: 0.01 = 10mm)")
    parser.add_argument("--max-poses", type=int, default=0,
                        help="Limit number of poses (0 = all, useful for debugging)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    robot_base = tuple(args.robot_base)

    # 1. Load pose.csv and convert to world-frame scalar-first
    raw_poses = load_pose_csv(args.pose_csv)
    if not raw_poses:
        sys.exit(f"No poses found in {args.pose_csv}")
    if args.max_poses > 0:
        raw_poses = raw_poses[:args.max_poses]
        logging.info(f"Limited to first {args.max_poses} poses (--max-poses)")

    poses = [
        convert_pose_to_world(*row, robot_base=robot_base)
        for row in raw_poses
    ]

    logging.info(f"Loaded {len(poses)} poses from {args.pose_csv}")
    logging.info(f"  robot base offset: {list(robot_base)}")
    logging.info(f"  first: world ({poses[0][0]:.4f}, {poses[0][1]:.4f}, {poses[0][2]:.4f})  qw={poses[0][3]:.4f}")
    logging.info(f"  last:  world ({poses[-1][0]:.4f}, {poses[-1][1]:.4f}, {poses[-1][2]:.4f})  qw={poses[-1][3]:.4f}")

    # 2. Create service
    service = WeldSeamOuterMoveService(
        poses=poses,
        velocity=args.velocity,
        acceleration=args.acceleration,
        blend_radius=args.blend_radius,
        motion_type=args.motion_type,
    )
    service.service_name = args.service_name

    # 3. Start gRPC server
    server, port = start_server(service)
    logging.info(f"gRPC server started on port {port}")

    # 4. Register with hub
    hub = HubCaller(args.hub)
    hub.register_service(service.service_type, service.service_name, port)
    logging.info(f"Registered '{service.service_name}' with hub at {args.hub}")
    logging.info(f"  motion_type={args.motion_type}  velocity={args.velocity}  "
                 f"blend_radius={args.blend_radius}")
    logging.info("")
    logging.info("Ready. Run Mech-Viz simulation — poses will be served at External Move step.")
    logging.info("Press Ctrl+C to stop.")

    # 5. Wait until interrupted
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        logging.info("Shutting down...")
        hub.unregister_service(service.service_name)
        server.stop(0)
        logging.info("Done.")


if __name__ == "__main__":
    main()
