import os
import sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from battery_case_gui import (
    build_comparison_display,
    build_live_capture_entry,
    capture_display_label,
    derive_viz_output_paths,
    describe_capture_entry,
    finalize_dts_e2e_verdict,
    guess_rgb_path,
    live_capture_id_from_raw_pcd,
    load_capture_registry,
    merge_capture_entries,
    parse_dts_e2e_output,
    recommended_variant_name,
    resolve_result_open_target,
    result_record_from_tree_item,
    resolve_canonical_eval_pcd,
    summarize_run_summary,
)


def test_capture_registry_loads() -> None:
    registry = load_capture_registry()
    assert "captures" in registry
    assert "978" in registry["captures"]


def test_resolve_canonical_eval_pcd_prefers_raw_capture() -> None:
    entry = {
        "raw_capture_ply": "/tmp/raw.ply",
        "roi_or_eval_pcd": "/tmp/roi.ply",
        "canonical_nn_evaluation_cloud": "raw_capture_ply",
    }
    assert resolve_canonical_eval_pcd(entry) == Path("/tmp/raw.ply")


def test_guess_rgb_path_from_raw_pcd(tmp_path: Path) -> None:
    raw = tmp_path / "point_cloud_20260317_134008_978.ply"
    rgb = tmp_path / "rgb_image_20260317_134008_978.png"
    raw.write_text("x", encoding="utf-8")
    rgb.write_text("x", encoding="utf-8")
    assert guess_rgb_path(raw) == rgb


def test_live_capture_id_from_raw_pcd_keeps_non_numeric_suffix(tmp_path: Path) -> None:
    raw = tmp_path / "point_cloud_20260319_120000_gui.ply"
    raw.write_text("x", encoding="utf-8")
    assert live_capture_id_from_raw_pcd(raw) == "20260319_120000_gui"


def test_build_live_capture_entry_marks_pending_icp(tmp_path: Path) -> None:
    raw = tmp_path / "point_cloud_20260319_120000_gui.ply"
    raw.write_text("x", encoding="utf-8")
    entry = build_live_capture_entry(raw)
    assert entry["icp_transform_npy"] is None
    assert entry["canonical_nn_evaluation_cloud"] == "raw_capture_ply"
    assert "아직 ICP 변환이 등록되지 않아" in " ".join(entry["notes"])


def test_capture_display_label_uses_explicit_label() -> None:
    entry = {"label": "978 · HDR 30° (기준)", "raw_capture_ply": "/tmp/978.ply", "icp_transform_npy": "/tmp/978.npy"}
    assert capture_display_label("978", entry) == "978 · HDR 30° (기준)"


def test_capture_display_label_generates_from_filename_for_live() -> None:
    entry = {"raw_capture_ply": "/tmp/point_cloud_20260319_120000_gui.ply", "icp_transform_npy": None}
    label = capture_display_label("live:gui", entry)
    assert "2026-03-19" in label
    assert "12:00" in label
    assert "pending ICP" in label


def test_capture_display_label_fallback_for_bare_id() -> None:
    entry = {"raw_capture_ply": "/tmp/some_other_name.ply", "icp_transform_npy": "/tmp/t.npy"}
    assert capture_display_label("abc", entry) == "abc"


def test_merge_capture_entries_adds_live_capture(tmp_path: Path) -> None:
    raw = tmp_path / "point_cloud_20260319_120000_gui.ply"
    raw.write_text("x", encoding="utf-8")
    registry = {
        "captures": {
            "978": {
                "raw_capture_ply": "/tmp/existing_978.ply",
                "roi_or_eval_pcd": None,
                "icp_transform_npy": "/tmp/978.npy",
                "canonical_nn_evaluation_cloud": "raw_capture_ply",
                "notes": [],
            }
        }
    }
    ids, entries = merge_capture_entries(registry, tmp_path)
    assert "978" in ids
    assert "20260319_120000_gui" in ids
    assert entries["20260319_120000_gui"]["_source"] == "live_capture_scan"


def test_summarize_run_summary_aggregates_scores() -> None:
    summary = {
        "results": [
            {
                "n_poses": 10,
                "score": {
                    "mean_nn_mm": 1.0,
                    "p90_nn_mm": 2.0,
                    "max_nn_mm": 3.0,
                    "centerline_p90_mm": 0.8,
                    "tangent_p90_deg": 6.0,
                    "corridor_inlier_ratio": 0.98,
                    "corridor_pass": True,
                },
            },
            {
                "n_poses": 20,
                "score": {
                    "mean_nn_mm": 2.0,
                    "p90_nn_mm": 4.0,
                    "max_nn_mm": 5.0,
                    "centerline_p90_mm": 1.2,
                    "tangent_p90_deg": 8.0,
                    "corridor_inlier_ratio": 0.96,
                    "corridor_pass": True,
                },
            },
        ]
    }
    agg = summarize_run_summary(summary)
    assert agg["avg_mean_nn_mm"] == 1.5
    assert agg["avg_p90_nn_mm"] == 3.0
    assert agg["worst_max_nn_mm"] == 5.0
    assert agg["avg_centerline_p90_mm"] == 1.0
    assert agg["avg_tangent_p90_deg"] == 7.0
    assert agg["avg_corridor_inlier_ratio"] == 0.97
    assert agg["corridor_pass"] is True
    assert agg["total_poses"] == 30.0


def test_recommended_variant_name_prefers_corrected_when_mean_improves() -> None:
    baseline = {
        "results": [{"n_poses": 10, "score": {"mean_nn_mm": 2.0, "p90_nn_mm": 3.0, "max_nn_mm": 4.0}}]
    }
    corrected = {
        "results": [{"n_poses": 10, "score": {"mean_nn_mm": 1.0, "p90_nn_mm": 2.5, "max_nn_mm": 4.2}}]
    }
    assert recommended_variant_name(baseline, corrected) == "corrected"


def test_recommended_variant_name_prefers_baseline_when_corrected_worse() -> None:
    baseline = {
        "results": [{"n_poses": 10, "score": {"mean_nn_mm": 1.0, "p90_nn_mm": 2.0, "max_nn_mm": 3.0}}]
    }
    corrected = {
        "results": [{"n_poses": 10, "score": {"mean_nn_mm": 1.4, "p90_nn_mm": 1.8, "max_nn_mm": 2.9}}]
    }
    assert recommended_variant_name(baseline, corrected) == "baseline"


def test_build_comparison_display_marks_small_gap_as_negligible() -> None:
    baseline = {
        "results": [{"n_poses": 10, "score": {"mean_nn_mm": 1.00, "p90_nn_mm": 1.50, "max_nn_mm": 2.00}}]
    }
    corrected = {
        "results": [{"n_poses": 10, "score": {"mean_nn_mm": 0.95, "p90_nn_mm": 1.42, "max_nn_mm": 1.90}}]
    }
    display = build_comparison_display(baseline, corrected, None)
    assert "실질 차이 미미" in display["headline"]
    assert "평균 NN Δ -0.050mm" in display["detail"]


def test_build_comparison_display_for_current_summary() -> None:
    current = {
        "variant": "corrected",
        "results": [{
            "n_poses": 24,
            "score": {
                "mean_nn_mm": 1.0,
                "p90_nn_mm": 1.8,
                "max_nn_mm": 2.1,
                "centerline_p90_mm": 0.9,
                "tangent_p90_deg": 7.5,
                "corridor_inlier_ratio": 0.97,
                "corridor_pass": True,
            },
        }],
    }
    display = build_comparison_display(None, None, current)
    assert display["headline"] == "현재 결과 · 보정안"
    assert "평균 NN 1.000mm" in display["detail"]
    assert "centerline P90 0.900mm" in display["detail"]
    assert "corridor 97.0%" in display["detail"]
    assert display["left"] == "총 포즈 수 24"


def test_derive_viz_output_paths_from_pose_csv(tmp_path: Path) -> None:
    pose_csv = tmp_path / "U1_right_pose.csv"
    outputs = derive_viz_output_paths(pose_csv)
    assert outputs["viz_csv"] == tmp_path / "U1_right_viz.csv"
    assert outputs["viz_csv"] == tmp_path / "U1_right_viz.csv"


def test_result_record_from_tree_item_extracts_expected_fields() -> None:
    tree_item = {
        "values": ("U1_right", "50", "0.599", "1.087", "2.223", "/tmp/U1_pose.csv", "/tmp/U1_1100.txt")
    }
    record = result_record_from_tree_item(tree_item, "U1_right")
    assert record["name"] == "U1_right"
    assert record["n_poses"] == 50
    assert record["mean_nn_mm"] == 0.599
    assert record["pose_csv"] == "/tmp/U1_pose.csv"


def test_parse_dts_e2e_output_extracts_summary_fields() -> None:
    text = """
[semi-auto] mocks are running
  log dir: C:\\Users\\hanmech\\AppData\\Local\\Temp\\dts-semi-auto-abc

[semi-auto] summary
  verdict: PASS
  gap mode: ok
  ok log grew: True
  ng log grew: False
"""
    parsed = parse_dts_e2e_output(text)
    assert parsed["verdict"] == "PASS"
    assert parsed["gap_mode"] == "ok"
    assert parsed["ok_log_grew"] is True
    assert parsed["ng_log_grew"] is False
    assert parsed["log_dir"] == r"C:\Users\hanmech\AppData\Local\Temp\dts-semi-auto-abc"


def test_parse_dts_e2e_output_extracts_log_sections() -> None:
    text = """[semi-auto] mocks are running
  log dir: C:\\Temp\\test

[semi-auto] summary
  verdict: PASS
  gap mode: ok
  ok log grew: True
  ng log grew: False

[robot.out]
recv 1100,45 poses
code=2100 reason=OK

[vision.out]
connected client 127.0.0.1
sent 45 poses

[ok.log tail]
2026-03-20 OK gap=0.12

[semi-auto] mocks stopped
"""
    parsed = parse_dts_e2e_output(text)
    assert parsed["verdict"] == "PASS"
    assert "sections" in parsed
    assert "robot.out" in parsed["sections"]
    assert "1100,45 poses" in parsed["sections"]["robot.out"]
    assert "vision.out" in parsed["sections"]
    assert "sent 45 poses" in parsed["sections"]["vision.out"]
    assert "ok.log tail" in parsed["sections"]
    assert "OK gap=0.12" in parsed["sections"]["ok.log tail"]


def test_describe_capture_entry_marks_fixed_capture_as_non_registerable() -> None:
    fixed_registry = {"captures": {"978": {"raw_capture_ply": "/tmp/978.ply"}}}
    entry = {
        "raw_capture_ply": "/tmp/978.ply",
        "icp_transform_npy": "/tmp/978.npy",
        "canonical_nn_evaluation_cloud": "raw_capture_ply",
    }
    info = describe_capture_entry("978", entry, fixed_registry)
    assert info["status"] == "fixed_ready"
    assert info["allow_icp_register"] is False


def test_describe_capture_entry_marks_pending_live_capture_as_registerable() -> None:
    fixed_registry = {"captures": {}}
    entry = {
        "raw_capture_ply": "/tmp/live.ply",
        "icp_transform_npy": None,
        "canonical_nn_evaluation_cloud": "raw_capture_ply",
        "_source": "live_capture_scan",
    }
    info = describe_capture_entry("live:1", entry, fixed_registry)
    assert info["status"] == "pending_icp"
    assert info["allow_icp_register"] is True


def test_finalize_dts_e2e_verdict_prefers_exit_code_failure() -> None:
    parsed = {"verdict": "PASS"}
    result = finalize_dts_e2e_verdict(parsed, returncode=1)
    assert result["verdict"] == "FAIL"
    assert result["reason"] == "exit_code=1"


def test_finalize_dts_e2e_verdict_uses_summary_when_exit_code_zero() -> None:
    parsed = {"verdict": "PASS"}
    result = finalize_dts_e2e_verdict(parsed, returncode=0)
    assert result["verdict"] == "PASS"
    assert result["reason"] == "summary"


def test_resolve_result_open_target_prefers_pose_column() -> None:
    record = {
        "pose_csv": "/tmp/U1_pose.csv",
        "txt_1100": "/tmp/U1_1100.txt",
    }
    summary = {"run_dir": "/tmp/run_dir"}
    assert resolve_result_open_target("#6", record, summary) == Path("/tmp/U1_pose.csv")


def test_resolve_result_open_target_defaults_to_run_dir() -> None:
    record = {
        "pose_csv": "/tmp/U1_pose.csv",
        "txt_1100": "/tmp/U1_1100.txt",
    }
    summary = {"run_dir": "/tmp/run_dir"}
    assert resolve_result_open_target("#1", record, summary) == Path("/tmp/run_dir")
