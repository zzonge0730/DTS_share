import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(__file__))
SAMPLING_DIR = os.path.join(
    ROOT, "DTS", "DTS", "Workspace", "DTS", "DTS", "FINAL_PJT"
)
sys.path.insert(0, SAMPLING_DIR)

try:
    import Sampling  # noqa: E402
except Exception:
    Sampling = None


def _pose(x, y, z=0.0):
    # [x,y,z,qx,qy,qz,qw] with identity quaternion
    return [float(x), float(y), float(z), 0.0, 0.0, 0.0, 1.0]


@unittest.skipUnless(Sampling is not None, "Sampling/numpy dependency not available")
class CurvatureSamplingTests(unittest.TestCase):
    def test_endpoints_are_preserved(self):
        poses = [_pose(i, 0) for i in range(30)]
        out = Sampling.curvature_adaptive_resample_with_quat(poses)
        self.assertEqual(out[0], poses[0])
        self.assertEqual(out[-1], poses[-1])

    def test_straight_line_is_downsampled(self):
        poses = [_pose(i, 0) for i in range(50)]
        out = Sampling.curvature_adaptive_resample_with_quat(
            poses,
            base_step_mm=5.0,
            min_step_mm=2.0,
            max_step_mm=8.0,
            angle_threshold_deg=8.0,
            curvature_gain=0.7,
        )
        self.assertLess(len(out), len(poses))

    def test_corner_keeps_anchor_points(self):
        # L-shape
        poses = [_pose(i, 0) for i in range(10)] + [_pose(9, j) for j in range(1, 10)]
        out = Sampling.curvature_adaptive_resample_with_quat(
            poses,
            base_step_mm=6.0,
            min_step_mm=1.0,
            max_step_mm=10.0,
            angle_threshold_deg=30.0,
            curvature_gain=0.9,
        )

        # turning anchor near (9,0) should be kept
        has_corner = any(abs(p[0] - 9.0) < 1e-6 and abs(p[1] - 0.0) < 1e-6 for p in out)
        self.assertTrue(has_corner)

    def test_smoothing_changes_xyz_only(self):
        poses = [_pose(i, 0.0) for i in range(7)]
        poses[3][1] = 10.0  # spike
        out = Sampling.smooth_positions(poses, window=5)

        # Quaternion fields unchanged.
        for p_in, p_out in zip(poses, out):
            self.assertEqual(p_in[3:], p_out[3:])

        # Spike should be reduced after smoothing.
        self.assertLess(out[3][1], poses[3][1])

    def test_invalid_shape_raises(self):
        with self.assertRaises(ValueError):
            Sampling.curvature_adaptive_resample_with_quat([[1, 2, 3]])


if __name__ == "__main__":
    unittest.main()
