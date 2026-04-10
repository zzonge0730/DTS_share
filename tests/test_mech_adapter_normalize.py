import os
import sys
import unittest
from math import cos, radians, sin


ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

from mock.mech_adapter_tcp import build_fallback_payload, normalize_to_1100


class MechAdapterNormalizeTests(unittest.TestCase):
    def test_fallback_payload_shape(self):
        payload = build_fallback_payload(3, step=10.0)
        parts = payload.split(",")
        self.assertEqual(parts[0], "1100")
        self.assertEqual(parts[1], "0003")
        self.assertEqual(len(parts), 2 + 3 * 6)

    def test_passthrough_valid_1100(self):
        raw = "1100,0002,1,2,3,4,5,6,7,8,9,10,11,12"
        out = normalize_to_1100(raw, default_count=7)
        self.assertEqual(out, "1100,0002,1,2,3,4,5,6,7,8,9,10,11,12")

    def test_1100_with_zero_count_infers_from_values(self):
        raw = "1100,0000,1,2,3,4,5,6,7,8,9,10,11,12"
        out = normalize_to_1100(raw, default_count=7)
        self.assertEqual(out, "1100,0002,1,2,3,4,5,6,7,8,9,10,11,12")

    def test_102_response_with_6_fields(self):
        raw = "102,1100,2,2,1,2,3,4,5,6,7,8,9,10,11,12"
        out = normalize_to_1100(raw, default_count=7)
        self.assertEqual(
            out,
            "1100,0002,1.000,2.000,3.000,4.000,5.000,6.000,7.000,8.000,9.000,10.000,11.000,12.000",
        )

    def test_102_response_with_8_fields_drops_extra_label_tool(self):
        # 2 poses, 8 fields each: x,y,z,rx,ry,rz,label,tool
        raw = "102,1100,2,2,1,2,3,4,5,6,101,201,7,8,9,10,11,12,102,202"
        out = normalize_to_1100(raw, default_count=7)
        self.assertEqual(
            out,
            "1100,0002,1.000,2.000,3.000,4.000,5.000,6.000,7.000,8.000,9.000,10.000,11.000,12.000",
        )

    def test_malformed_102_falls_back(self):
        raw = "102,1100,2,2,1,2,3"
        out = normalize_to_1100(raw, default_count=3)
        self.assertEqual(out, build_fallback_payload(3))

    def test_205_response_with_6_fields(self):
        raw = "205,2100,2,2,1,2,3,4,5,6,7,8,9,10,11,12"
        out = normalize_to_1100(raw, default_count=7)
        self.assertEqual(
            out,
            "1100,0002,1.000,2.000,3.000,4.000,5.000,6.000,7.000,8.000,9.000,10.000,11.000,12.000",
        )

    def test_205_response_with_8_fields_drops_extra_label_tool(self):
        raw = "205,2100,2,2,1,2,3,4,5,6,101,201,7,8,9,10,11,12,102,202"
        out = normalize_to_1100(raw, default_count=7)
        self.assertEqual(
            out,
            "1100,0002,1.000,2.000,3.000,4.000,5.000,6.000,7.000,8.000,9.000,10.000,11.000,12.000",
        )

    def test_malformed_205_falls_back(self):
        raw = "205,2100,2,2,1,2,3"
        out = normalize_to_1100(raw, default_count=3)
        self.assertEqual(out, build_fallback_payload(3))

    def test_102_response_with_7_fields_identity_quat(self):
        raw = "102,1100,2,1,1,2,3,1,0,0,0"
        out = normalize_to_1100(raw, default_count=7)
        self.assertEqual(out, "1100,0001,1.000,2.000,3.000,0.000,0.000,0.000")

    def test_102_response_with_7_fields_x_90deg_quat(self):
        h = radians(90.0) / 2.0
        qw = cos(h)
        qx = sin(h)
        raw = f"102,1100,2,1,1,2,3,{qw},{qx},0,0"
        out = normalize_to_1100(raw, default_count=7)
        self.assertEqual(out, "1100,0001,1.000,2.000,3.000,90.000,0.000,0.000")

    def test_102_response_with_7_fields_y_90deg_quat(self):
        h = radians(90.0) / 2.0
        qw = cos(h)
        qy = sin(h)
        raw = f"102,1100,2,1,1,2,3,{qw},0,{qy},0"
        out = normalize_to_1100(raw, default_count=7)
        self.assertEqual(out, "1100,0001,1.000,2.000,3.000,0.000,90.000,0.000")

    def test_102_response_with_7_fields_z_90deg_quat(self):
        h = radians(90.0) / 2.0
        qw = cos(h)
        qz = sin(h)
        raw = f"102,1100,2,1,1,2,3,{qw},0,0,{qz}"
        out = normalize_to_1100(raw, default_count=7)
        self.assertEqual(out, "1100,0001,1.000,2.000,3.000,0.000,0.000,90.000")

    def test_102_response_with_7_fields_gimbal_lock_boundary(self):
        h = radians(89.999) / 2.0
        qw = cos(h)
        qy = sin(h)
        raw = f"102,1100,2,1,1,2,3,{qw},0,{qy},0"
        out = normalize_to_1100(raw, default_count=7)
        self.assertEqual(out, "1100,0001,1.000,2.000,3.000,0.000,89.999,0.000")

    def test_unknown_code_falls_back(self):
        raw = "9999,foo,bar"
        out = normalize_to_1100(raw, default_count=2)
        self.assertEqual(out, build_fallback_payload(2))

    def test_unknown_code_fail_safe_returns_empty(self):
        raw = "9999,foo,bar"
        out = normalize_to_1100(raw, default_count=2, allow_fallback=False)
        self.assertEqual(out, "")

    def test_malformed_1100_fail_safe_returns_empty(self):
        raw = "1100,0002,1,2,3"
        out = normalize_to_1100(raw, default_count=2, allow_fallback=False)
        self.assertEqual(out, "")


if __name__ == "__main__":
    unittest.main()
