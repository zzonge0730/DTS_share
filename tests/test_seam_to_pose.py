import math
import os
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import numpy as np
except Exception:
    np = None

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from seam_to_pose import (
    Pose6D,
    build_poses,
    compute_tangent_vectors,
    estimate_surface_normal,
    format_1100,
    load_seam_csv,
    resample_uniform,
    rotation_matrix_to_euler_zyx,
)


@unittest.skipUnless(np is not None, "numpy dependency not available")
class ResampleTests(unittest.TestCase):
    def test_single_point_unchanged(self):
        pts = np.array([[1.0, 2.0, 3.0]])
        out = resample_uniform(pts, step=10.0)
        np.testing.assert_array_equal(out, pts)

    def test_straight_line_count(self):
        """100mm line with 10mm step -> 11 points."""
        pts = np.array([[0, 0, 0], [100, 0, 0]], dtype=float)
        out = resample_uniform(pts, step=10.0)
        self.assertEqual(len(out), 11)

    def test_straight_line_endpoints(self):
        pts = np.array([[0, 0, 0], [100, 0, 0]], dtype=float)
        out = resample_uniform(pts, step=10.0)
        np.testing.assert_allclose(out[0], [0, 0, 0], atol=1e-9)
        np.testing.assert_allclose(out[-1], [100, 0, 0], atol=1e-9)

    def test_l_shape_total_length(self):
        """L-shape: 200mm + 200mm = 400mm total."""
        pts = np.array([[0, 0, 0], [200, 0, 0], [200, 200, 0]], dtype=float)
        out = resample_uniform(pts, step=10.0)
        diffs = np.diff(out, axis=0)
        total = np.sum(np.linalg.norm(diffs, axis=1))
        self.assertAlmostEqual(total, 400.0, places=1)


@unittest.skipUnless(np is not None, "numpy dependency not available")
class TangentTests(unittest.TestCase):
    def test_straight_line_tangents(self):
        pts = np.array([[0, 0, 0], [10, 0, 0], [20, 0, 0]], dtype=float)
        tangents = compute_tangent_vectors(pts)
        for t in tangents:
            np.testing.assert_allclose(t, [1, 0, 0], atol=1e-9)

    def test_tangent_unit_length(self):
        pts = np.array([[0, 0, 0], [3, 4, 0], [6, 8, 0]], dtype=float)
        tangents = compute_tangent_vectors(pts)
        for t in tangents:
            self.assertAlmostEqual(np.linalg.norm(t), 1.0, places=9)


@unittest.skipUnless(np is not None, "numpy dependency not available")
class NormalTests(unittest.TestCase):
    def test_xy_plane_normal_is_z(self):
        pts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]], dtype=float)
        normal = estimate_surface_normal(pts)
        self.assertAlmostEqual(abs(normal[2]), 1.0, places=6)

    def test_two_points_fallback_z(self):
        pts = np.array([[0, 0, 0], [1, 0, 0]], dtype=float)
        normal = estimate_surface_normal(pts)
        np.testing.assert_array_equal(normal, [0, 0, 1])


@unittest.skipUnless(np is not None, "numpy dependency not available")
class EulerTests(unittest.TestCase):
    def test_identity_gives_zero(self):
        rx, ry, rz = rotation_matrix_to_euler_zyx(np.eye(3))
        self.assertAlmostEqual(rx, 0.0, places=6)
        self.assertAlmostEqual(ry, 0.0, places=6)
        self.assertAlmostEqual(rz, 0.0, places=6)

    def test_90deg_z_rotation(self):
        R = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]], dtype=float)
        rx, ry, rz = rotation_matrix_to_euler_zyx(R)
        self.assertAlmostEqual(rz, 90.0, places=4)
        self.assertAlmostEqual(rx, 0.0, places=4)
        self.assertAlmostEqual(ry, 0.0, places=4)

    def test_gimbal_lock_pitch_90_is_stable(self):
        R = np.array([[0, 0, 1], [0, 1, 0], [-1, 0, 0]], dtype=float)
        rx, ry, rz = rotation_matrix_to_euler_zyx(R)
        self.assertTrue(math.isfinite(rx))
        self.assertAlmostEqual(ry, 90.0, places=4)
        self.assertAlmostEqual(rz, 0.0, places=4)


@unittest.skipUnless(np is not None, "numpy dependency not available")
class BuildPoseTests(unittest.TestCase):
    def test_pose_count_matches_points(self):
        pts = np.array([[0, 0, 0], [10, 0, 0], [20, 0, 0]], dtype=float)
        tangents = compute_tangent_vectors(pts)
        normal = np.array([0, 0, 1.0])
        poses = build_poses(pts, tangents, normal)
        self.assertEqual(len(poses), 3)

    def test_pose_xyz_matches_input(self):
        pts = np.array([[100, 200, 300], [110, 200, 300]], dtype=float)
        tangents = compute_tangent_vectors(pts)
        normal = np.array([0, 0, 1.0])
        poses = build_poses(pts, tangents, normal)
        self.assertAlmostEqual(poses[0].x, 100.0)
        self.assertAlmostEqual(poses[0].y, 200.0)
        self.assertAlmostEqual(poses[0].z, 300.0)

    def test_parallel_tangent_and_normal_uses_safe_fallback_axis(self):
        pts = np.array([[0, 0, 0], [10, 0, 0]], dtype=float)
        tangents = compute_tangent_vectors(pts)
        poses = build_poses(pts, tangents, np.array([1.0, 0.0, 0.0]))
        self.assertEqual(len(poses), 2)
        for pose in poses:
            self.assertTrue(math.isfinite(pose.rx))
            self.assertTrue(math.isfinite(pose.ry))
            self.assertTrue(math.isfinite(pose.rz))


@unittest.skipUnless(np is not None, "numpy dependency not available")
class InputValidationTests(unittest.TestCase):
    def test_load_seam_csv_empty_raises(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write("x,y,z\n")
            path = Path(f.name)
        self.addCleanup(lambda: path.exists() and path.unlink())

        with self.assertRaises(ValueError):
            load_seam_csv(path)


@unittest.skipUnless(np is not None, "numpy dependency not available")
class Format1100Tests(unittest.TestCase):
    def test_header_count(self):
        poses = [Pose6D(1, 2, 3, 4, 5, 6), Pose6D(7, 8, 9, 10, 11, 12)]
        result = format_1100(poses)
        self.assertTrue(result.startswith("1100,2,"))

    def test_single_pose_format(self):
        poses = [Pose6D(1.5, 2.5, 3.5, 10.0, 20.0, 30.0)]
        result = format_1100(poses)
        self.assertEqual(result, "1100,1,1.500,2.500,3.500,10.000,20.000,30.000")


if __name__ == "__main__":
    unittest.main()
