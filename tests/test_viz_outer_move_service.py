import csv
import math
import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from viz_outer_move_service import (
    TCP_POSE,
    WeldSeamOuterMoveService,
    _euler_zyx_to_quat,
    convert_pose_to_world,
    load_pose_csv,
    load_viz_csv,
)


class VizOuterMoveServiceTests(unittest.TestCase):
    def test_load_pose_csv_reads_six_columns(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["x", "y", "z", "rx", "ry", "rz"])
            writer.writerow(["100.0", "200.0", "300.0", "10.0", "20.0", "30.0"])
            path = Path(f.name)
        self.addCleanup(lambda: path.exists() and path.unlink())

        rows = load_pose_csv(path)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0], [100.0, 200.0, 300.0, 10.0, 20.0, 30.0])

    def test_load_viz_csv_reads_scalar_last_rows(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["x_m", "y_m", "z_m", "qx", "qy", "qz", "qw"])
            writer.writerow(["0.1", "0.2", "0.3", "0.4", "0.5", "0.6", "0.7"])
            path = Path(f.name)
        self.addCleanup(lambda: path.exists() and path.unlink())

        poses = load_viz_csv(path)
        self.assertEqual(poses, [[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]])

    def test_euler_zyx_to_quat_identity(self):
        qw, qx, qy, qz = _euler_zyx_to_quat(0, 0, 0)
        self.assertAlmostEqual(qw, 1.0)
        self.assertAlmostEqual(qx, 0.0)
        self.assertAlmostEqual(qy, 0.0)
        self.assertAlmostEqual(qz, 0.0)

    def test_euler_zyx_to_quat_90deg_rx(self):
        qw, qx, qy, qz = _euler_zyx_to_quat(90, 0, 0)
        self.assertAlmostEqual(qw, math.cos(math.pi / 4), places=5)
        self.assertAlmostEqual(qx, math.sin(math.pi / 4), places=5)
        self.assertAlmostEqual(qy, 0.0, places=5)
        self.assertAlmostEqual(qz, 0.0, places=5)

    def test_convert_pose_to_world_applies_offset_and_scalar_first(self):
        # Identity orientation, 1000mm offset in x
        result = convert_pose_to_world(
            1000.0, 2000.0, 3000.0,  # mm
            0.0, 0.0, 0.0,          # deg (identity)
            robot_base=(1.3, -0.5, 0.0),
        )
        # x: 1.0 + 1.3 = 2.3, y: 2.0 + (-0.5) = 1.5, z: 3.0 + 0.0 = 3.0
        self.assertAlmostEqual(result[0], 2.3)
        self.assertAlmostEqual(result[1], 1.5)
        self.assertAlmostEqual(result[2], 3.0)
        # Identity quaternion: qw=1, qx=qy=qz=0
        self.assertAlmostEqual(result[3], 1.0)  # qw
        self.assertAlmostEqual(result[4], 0.0)  # qx
        self.assertAlmostEqual(result[5], 0.0)  # qy
        self.assertAlmostEqual(result[6], 0.0)  # qz

    def test_service_returns_one_target_per_call(self):
        """One pose per call, poses already in world-frame scalar-first."""
        poses = [
            [1.1, 0.2, 0.3, 0.7, 0.4, 0.5, 0.6],  # [x,y,z, qw,qx,qy,qz]
            [2.1, 1.2, 1.3, 0.8, 0.3, 0.2, 0.1],
        ]
        service = WeldSeamOuterMoveService(poses=poses)

        first = service.getMoveTargets({"di": None, "joint_positions": [], "pose": []})
        second = service.getMoveTargets({"di": None, "joint_positions": [], "pose": []})
        third = service.getMoveTargets({"di": None, "joint_positions": [], "pose": []})

        # Call 1: pose 0 passed directly
        self.assertEqual(len(first["targets"]), 1)
        self.assertEqual(first["targets"][0]["move_target_type"], TCP_POSE)
        self.assertEqual(first["targets"][0]["target"], poses[0])

        # Call 2: pose 1
        self.assertEqual(len(second["targets"]), 1)
        self.assertEqual(second["targets"][0]["target"], poses[1])

        # Call 3: all delivered, empty
        self.assertEqual(third["targets"], [])


if __name__ == "__main__":
    unittest.main()
