import os
import sys
import unittest
from math import cos, pi, sin

try:
    import numpy as np
except Exception:
    np = None


ROOT = os.path.dirname(os.path.dirname(__file__))
FINAL_PJT = os.path.join(ROOT, "DTS", "DTS", "Workspace", "DTS", "DTS", "FINAL_PJT")
sys.path.insert(0, FINAL_PJT)

from main import _filter_pose_outliers_drop, _rotation_jump_indices, apply_rigid_transform


@unittest.skipUnless(np is not None, "numpy dependency not available")
class RigidTransformTests(unittest.TestCase):
    def test_identity_transform_keeps_pose(self):
        poses = [[1.0, 2.0, 3.0, 1.0, 0.0, 0.0, 0.0]]
        out = np.asarray(apply_rigid_transform(poses, np.eye(4)), dtype=float)
        np.testing.assert_allclose(out, np.asarray(poses, dtype=float), atol=1e-9)

    def test_translation_moves_xyz_only(self):
        poses = [[1.0, 2.0, 3.0, 1.0, 0.0, 0.0, 0.0]]
        T = np.eye(4, dtype=float)
        T[:3, 3] = [10.0, -5.0, 2.0]
        out = np.asarray(apply_rigid_transform(poses, T), dtype=float)
        np.testing.assert_allclose(out[0, :3], [11.0, -3.0, 5.0], atol=1e-9)
        np.testing.assert_allclose(out[0, 3:], [1.0, 0.0, 0.0, 0.0], atol=1e-9)

    def test_z90_rotation_rotates_xyz_and_quaternion(self):
        poses = [[1.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]]
        c = cos(pi / 2.0)
        s = sin(pi / 2.0)
        T = np.array(
            [
                [c, -s, 0.0, 0.0],
                [s, c, 0.0, 0.0],
                [0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0, 1.0],
            ],
            dtype=float,
        )

        out = np.asarray(apply_rigid_transform(poses, T), dtype=float)
        np.testing.assert_allclose(out[0, :3], [0.0, 1.0, 0.0], atol=1e-9)

        expected_q = np.array([cos(pi / 4.0), 0.0, 0.0, sin(pi / 4.0)], dtype=float)
        if np.dot(out[0, 3:], expected_q) < 0:
            expected_q = -expected_q
        np.testing.assert_allclose(out[0, 3:], expected_q, atol=1e-6)

    def test_rotation_jump_detection(self):
        q_id = [1.0, 0.0, 0.0, 0.0]
        q_z_180 = [0.0, 0.0, 0.0, 1.0]
        poses = [
            [0.0, 0.0, 0.0, *q_id],
            [1.0, 0.0, 0.0, *q_id],
            [2.0, 0.0, 0.0, *q_z_180],
        ]
        jumps = _rotation_jump_indices(poses, threshold_deg=30.0)
        self.assertEqual(jumps, [1])

    def test_outlier_drop_removes_single_spike(self):
        q_id = [1.0, 0.0, 0.0, 0.0]
        q_z_180 = [0.0, 0.0, 0.0, 1.0]
        poses = [
            [0.0, 0.0, 0.0, *q_id],
            [1.0, 0.0, 0.0, *q_id],
            [2.0, 0.0, 0.0, *q_z_180],
            [3.0, 0.0, 0.0, *q_id],
        ]
        out, info = _filter_pose_outliers_drop(poses, threshold_deg=30.0, max_ratio=0.8)
        self.assertEqual(info["removed"], 2)
        self.assertEqual(len(out), 2)

    def test_outlier_drop_fail_safe_when_ratio_too_high(self):
        q_id = [1.0, 0.0, 0.0, 0.0]
        q_z_180 = [0.0, 0.0, 0.0, 1.0]
        poses = [
            [0.0, 0.0, 0.0, *q_id],
            [1.0, 0.0, 0.0, *q_z_180],
            [2.0, 0.0, 0.0, *q_id],
            [3.0, 0.0, 0.0, *q_z_180],
        ]
        with self.assertRaises(RuntimeError):
            _filter_pose_outliers_drop(poses, threshold_deg=30.0, max_ratio=0.2)


if __name__ == "__main__":
    unittest.main()
