import argparse
import json
import os
import shutil
import tempfile
import time
from datetime import datetime, timedelta


def build_payload(mode: str, part_id: str):
    now = datetime.now()
    ts = now
    if mode == "stale":
        ts = now - timedelta(seconds=20)

    if mode == "ok":
        max_gap, avg_gap, rms_gap = 0.8, 0.5, 0.55
        icp_fitness, icp_inlier_rmse = 0.95, 0.35
    elif mode == "ng":
        max_gap, avg_gap, rms_gap = 3.2, 1.8, 2.1
        icp_fitness, icp_inlier_rmse = 0.93, 0.4
    elif mode == "ng_avg":
        max_gap, avg_gap, rms_gap = 1.5, 1.5, 1.3
        icp_fitness, icp_inlier_rmse = 0.95, 0.35
    elif mode == "icp_low":
        max_gap, avg_gap, rms_gap = 0.7, 0.4, 0.5
        icp_fitness, icp_inlier_rmse = 0.12, 0.35
    elif mode == "icp_high":
        max_gap, avg_gap, rms_gap = 0.7, 0.4, 0.5
        icp_fitness, icp_inlier_rmse = 0.95, 2.2
    elif mode == "icp_bad":
        # Gap values are in tolerance, but ICP quality is poor.
        max_gap, avg_gap, rms_gap = 0.7, 0.4, 0.5
        icp_fitness, icp_inlier_rmse = 0.12, 2.2
    elif mode == "icp_missing":
        max_gap, avg_gap, rms_gap = 0.7, 0.4, 0.5
        icp_fitness, icp_inlier_rmse = None, None
    elif mode == "invalid":
        max_gap, avg_gap, rms_gap = "nan", 0.0, 0.0
        icp_fitness, icp_inlier_rmse = 0.0, 0.0
    else:
        max_gap, avg_gap, rms_gap = 1.0, 0.6, 0.7
        icp_fitness, icp_inlier_rmse = 0.9, 0.6

    metrics = {
        "max_gap_mm": max_gap,
        "avg_gap_mm": avg_gap,
        "rms_gap_mm": rms_gap,
        "samples": 300,
    }
    quality = {
        "source": "mock_gap_writer.py",
        "confidence": 1.0,
    }
    if icp_fitness is not None:
        metrics["icp_fitness"] = icp_fitness
        quality["icp_fitness"] = icp_fitness
    if icp_inlier_rmse is not None:
        metrics["icp_inlier_rmse"] = icp_inlier_rmse
        quality["icp_inlier_rmse"] = icp_inlier_rmse

    return {
        "session_id": f"mock-{int(time.time())}",
        "part_id": part_id,
        "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3],
        "metrics": metrics,
        "quality": quality,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/tmp/gap_input.json")
    ap.add_argument(
        "--mode",
        choices=["ok", "ng", "ng_avg", "stale", "invalid", "icp_bad", "icp_low", "icp_high", "icp_missing"],
        default="ok",
    )
    ap.add_argument("--part-id", default="mock-part")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--interval", type=float, default=0.5)
    args = ap.parse_args()

    out_dir = os.path.dirname(os.path.abspath(args.out))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    while True:
        payload = build_payload(args.mode, args.part_id)
        temp_path = ""
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=out_dir,
                suffix=".json",
                delete=False,
            ) as f:
                temp_path = f.name
                json.dump(payload, f, ensure_ascii=True, indent=2)
                f.flush()
                os.fsync(f.fileno())
            shutil.move(temp_path, args.out)
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
        print(f"[gap-writer] wrote {args.mode}: {args.out}")

        if args.once:
            break
        time.sleep(max(0.1, args.interval))


if __name__ == "__main__":
    main()
