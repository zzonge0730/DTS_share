import math
import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from transforms import (
    euler_zyx_to_rotation_matrix,
    quat_to_euler_zyx,
    rotation_matrix_to_euler_zyx,
    rotation_matrix_to_quaternion,
)


class SharedTransformTests(unittest.TestCase):
    def test_identity_matrix_to_quaternion(self):
        qw, qx, qy, qz = rotation_matrix_to_quaternion(
            ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
        )
        self.assertAlmostEqual(qw, 1.0, places=6)
        self.assertAlmostEqual(qx, 0.0, places=6)
        self.assertAlmostEqual(qy, 0.0, places=6)
        self.assertAlmostEqual(qz, 0.0, places=6)

    def test_z90_round_trip(self):
        R = euler_zyx_to_rotation_matrix(0.0, 0.0, 90.0)
        qw, qx, qy, qz = rotation_matrix_to_quaternion(R)
        rx, ry, rz = quat_to_euler_zyx(qw, qx, qy, qz)
        self.assertAlmostEqual(rx, 0.0, places=4)
        self.assertAlmostEqual(ry, 0.0, places=4)
        self.assertAlmostEqual(rz, 90.0, places=4)

    def test_matrix_to_euler_gimbal_lock_boundary(self):
        R = (
            (0.0, 0.0, 1.0),
            (0.0, 1.0, 0.0),
            (-1.0, 0.0, 0.0),
        )
        rx, ry, rz = rotation_matrix_to_euler_zyx(R)
        self.assertTrue(math.isfinite(rx))
        self.assertAlmostEqual(ry, 90.0, places=4)
        self.assertAlmostEqual(rz, 0.0, places=4)


if __name__ == "__main__":
    unittest.main()
