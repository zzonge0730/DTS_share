import os
import sys
import unittest
from datetime import datetime


ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

from mock.mock_gap_writer import build_payload


def _evaluate_like_form1(
    payload,
    max_tol=2.0,
    avg_tol=1.0,
    icp_quality_enforce=False,
    icp_fitness_min=0.3,
    icp_inlier_rmse_max=1.5,
):
    try:
        metrics = payload.get("metrics", {})
        if int(metrics.get("samples", 0)) <= 0:
            return ("NG", "NO_RESULT")

        max_gap = float(metrics["max_gap_mm"])
        avg_gap = float(metrics["avg_gap_mm"])
        rms_gap = float(metrics["rms_gap_mm"])
        _ = rms_gap
        if not all(map(lambda v: v == v and abs(v) != float("inf"), [max_gap, avg_gap, rms_gap])):
            return ("NG", "INVALID_GAP_DATA")

        ts = payload.get("timestamp")
        if ts:
            datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%f")

        if max_gap > max_tol:
            return ("NG", "GAP_EXCEED_MAX")
        if avg_gap > avg_tol:
            return ("NG", "GAP_EXCEED_AVG")

        if icp_quality_enforce:
            quality = payload.get("quality", {})
            icp_fitness = metrics.get("icp_fitness", quality.get("icp_fitness"))
            icp_rmse = metrics.get("icp_inlier_rmse", quality.get("icp_inlier_rmse"))
            if icp_fitness is None or icp_rmse is None:
                return ("NG", "ICP_METRIC_MISSING")
            if float(icp_fitness) < icp_fitness_min:
                return ("NG", "ICP_FITNESS_LOW")
            if float(icp_rmse) > icp_inlier_rmse_max:
                return ("NG", "ICP_RMSE_HIGH")

        return ("OK", "WITHIN_TOL")
    except Exception:
        return ("NG", "INVALID_GAP_DATA")


class GapIcpGateHeadlessTests(unittest.TestCase):
    def test_ok_without_icp_enforce(self):
        p = build_payload("ok", "part")
        self.assertEqual(_evaluate_like_form1(p, icp_quality_enforce=False), ("OK", "WITHIN_TOL"))

    def test_ok_with_icp_enforce(self):
        p = build_payload("ok", "part")
        self.assertEqual(_evaluate_like_form1(p, icp_quality_enforce=True), ("OK", "WITHIN_TOL"))

    def test_ng_by_gap_max(self):
        p = build_payload("ng", "part")
        self.assertEqual(_evaluate_like_form1(p, icp_quality_enforce=True), ("NG", "GAP_EXCEED_MAX"))

    def test_icp_bad_ignored_when_enforce_disabled(self):
        p = build_payload("icp_bad", "part")
        self.assertEqual(_evaluate_like_form1(p, icp_quality_enforce=False), ("OK", "WITHIN_TOL"))

    def test_icp_bad_blocked_when_enforce_enabled(self):
        p = build_payload("icp_bad", "part")
        self.assertEqual(_evaluate_like_form1(p, icp_quality_enforce=True), ("NG", "ICP_FITNESS_LOW"))

    def test_icp_missing_blocked_when_enforce_enabled(self):
        p = build_payload("icp_missing", "part")
        self.assertEqual(_evaluate_like_form1(p, icp_quality_enforce=True), ("NG", "ICP_METRIC_MISSING"))

    def test_invalid_payload_blocked(self):
        p = build_payload("invalid", "part")
        self.assertEqual(_evaluate_like_form1(p, icp_quality_enforce=True), ("NG", "INVALID_GAP_DATA"))


if __name__ == "__main__":
    unittest.main()
