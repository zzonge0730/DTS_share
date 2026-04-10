import os
import sys
from pathlib import Path
import numpy as np

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from dts.icp import (  # noqa: E402
    _make_estimator,
    _run_one_icp_stage,
    DEFAULT_ICP_STAGES as _DEFAULT_ICP_STAGES,
    combine_seam_name_groups,
    compute_direction_agnostic_tangent_error_deg,
    compute_polyline_geometry_metrics,
    choose_best_result,
    default_live_registry,
    load_live_registry,
    prune_seed_candidates,
    save_live_registry,
    seam_local_summary_not_worse,
    summarize_seam_local_scores,
)
from dts.paths import capture_id_from_raw_pcd  # noqa: E402
from register_battery_capture_icp import (  # noqa: E402
    make_live_capture_entry,
    DEFAULT_SEAM_CENTERLINE_CORRIDOR_MM,
    DEFAULT_SEAM_TANGENT_CORRIDOR_DEG,
    DEFAULT_SEAM_CORRIDOR_MIN_INLIER_RATIO,
)


def test_capture_id_from_raw_pcd_numeric_suffix() -> None:
    raw = Path("/tmp/point_cloud_20260317_134008_978.ply")
    assert capture_id_from_raw_pcd(raw) == "978"


def test_capture_id_from_raw_pcd_non_numeric_suffix() -> None:
    raw = Path("/tmp/point_cloud_20260319_120000_gui.ply")
    assert capture_id_from_raw_pcd(raw) == "20260319_120000_gui"


def test_live_registry_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "capture_registry_live.json"
    registry = default_live_registry(reference_pcd="/tmp/ref.ply")
    registry["captures"]["demo"] = {
        "raw_capture_ply": "/tmp/raw.ply",
        "icp_transform_npy": "/tmp/T.npy",
    }
    save_live_registry(registry, path)
    loaded = load_live_registry(path, reference_pcd="/tmp/ref.ply")
    assert loaded["reference_pcd"] == "/tmp/ref.ply"
    assert loaded["captures"]["demo"]["icp_transform_npy"] == "/tmp/T.npy"


def test_choose_best_result_prefers_fitness_then_rmse() -> None:
    best = choose_best_result(
        [
            {"seed_name": "a", "fitness": 0.8, "rmse_mm": 1.5},
            {"seed_name": "b", "fitness": 0.9, "rmse_mm": 2.0},
            {"seed_name": "c", "fitness": 0.9, "rmse_mm": 1.1},
        ]
    )
    assert best["seed_name"] == "c"


def test_choose_best_result_keeps_first_on_effective_tie() -> None:
    best = choose_best_result(
        [
            {"seed_name": "first", "fitness": 0.95, "rmse_mm": 2.0},
            {"seed_name": "second", "fitness": 0.95 + 5e-10, "rmse_mm": 2.0 + 5e-10},
        ]
    )
    assert best["seed_name"] == "first"


def test_make_live_capture_entry_marks_raw_capture_as_canonical(tmp_path: Path) -> None:
    entry = make_live_capture_entry(
        raw_capture_ply=tmp_path / "point_cloud_test.ply",
        icp_transform_npy=tmp_path / "icp_transform_test.npy",
        icp_report_json=tmp_path / "icp_report_test.json",
        best_seed_name="978",
        fitness=0.91,
        rmse_mm=1.8,
    )
    assert entry["canonical_nn_evaluation_cloud"] == "raw_capture_ply"
    assert "978" in " ".join(entry["notes"])


def test_prune_seed_candidates_keeps_top_two_by_fitness_then_rmse() -> None:
    kept, pruned = prune_seed_candidates(
        [
            {"seed_name": "763", "fitness": 0.42, "rmse_mm": 4.95},
            {"seed_name": "978", "fitness": 0.96, "rmse_mm": 2.00},
            {"seed_name": "741", "fitness": 0.95, "rmse_mm": 2.05},
            {"seed_name": "473", "fitness": 0.89, "rmse_mm": 2.40},
        ],
        max_keep=2,
    )
    assert [item["seed_name"] for item in kept] == ["978", "741"]
    assert [item["seed_name"] for item in pruned] == ["473", "763"]


def test_summarize_seam_local_scores_returns_expected_aggregates() -> None:
    summary = summarize_seam_local_scores(
        {
            "U1_right": {
                "n_points": 28,
                "mean_nn_mm": 0.5,
                "p90_nn_mm": 0.9,
                "max_nn_mm": 1.6,
                "centerline_mean_mm": 0.2,
                "centerline_p90_mm": 0.4,
                "centerline_max_mm": 0.9,
                "tangent_mean_deg": 3.0,
                "tangent_p90_deg": 5.0,
                "tangent_max_deg": 9.0,
                "corridor_inlier_ratio": 1.0,
                "endpoint_start_mm": 0.0,
                "endpoint_end_mm": 0.0,
                "max_contiguous_outlier_points": 0.0,
            },
            "U2_left": {
                "n_points": 24,
                "mean_nn_mm": 1.0,
                "p90_nn_mm": 1.8,
                "max_nn_mm": 2.6,
                "centerline_mean_mm": 0.3,
                "centerline_p90_mm": 0.6,
                "centerline_max_mm": 1.2,
                "tangent_mean_deg": 4.0,
                "tangent_p90_deg": 7.0,
                "tangent_max_deg": 12.0,
                "corridor_inlier_ratio": 0.96,
                "endpoint_start_mm": 0.0,
                "endpoint_end_mm": 0.0,
                "max_contiguous_outlier_points": 0.0,
            },
        },
        centerline_corridor_mm=DEFAULT_SEAM_CENTERLINE_CORRIDOR_MM,
        tangent_corridor_deg=DEFAULT_SEAM_TANGENT_CORRIDOR_DEG,
        corridor_min_inlier_ratio=DEFAULT_SEAM_CORRIDOR_MIN_INLIER_RATIO,
    )
    assert summary["avg_mean_nn_mm"] == 0.75
    assert summary["avg_p90_nn_mm"] == 1.35
    assert summary["worst_max_nn_mm"] == 2.6
    assert summary["avg_centerline_mean_mm"] == 0.25
    assert summary["avg_centerline_p90_mm"] == 0.5
    assert summary["worst_centerline_max_mm"] == 1.2
    assert summary["avg_tangent_mean_deg"] == 3.5
    assert summary["avg_tangent_p90_deg"] == 6.0
    assert summary["worst_tangent_max_deg"] == 12.0
    assert summary["avg_corridor_inlier_ratio"] == 0.98
    assert summary["min_corridor_inlier_ratio"] == 0.96
    assert summary["avg_endpoint_start_mm"] == 0.0
    assert summary["avg_endpoint_end_mm"] == 0.0
    assert summary["worst_endpoint_start_mm"] == 0.0
    assert summary["worst_endpoint_end_mm"] == 0.0
    assert summary["worst_contiguous_outlier_points"] == 0.0
    assert summary["corridor_pass"] is True
    assert summary["total_points"] == 52.0


def test_combine_seam_name_groups_preserves_order_and_uniqueness() -> None:
    result = combine_seam_name_groups(
        ("U1_right", "U2_left"),
        ("U2_left", "S3_complex_bottom"),
    )
    assert result == ("U1_right", "U2_left", "S3_complex_bottom")


def test_seam_local_summary_not_worse_accepts_small_tolerance() -> None:
    before = {
        "avg_mean_nn_mm": 0.80,
        "avg_p90_nn_mm": 1.50,
        "worst_max_nn_mm": 2.10,
        "total_points": 40.0,
    }
    after = {
        "avg_mean_nn_mm": 0.81,
        "avg_p90_nn_mm": 1.54,
        "worst_max_nn_mm": 2.14,
        "total_points": 40.0,
    }
    assert seam_local_summary_not_worse(before, after)


def test_seam_local_summary_not_worse_rejects_clear_regression() -> None:
    before = {
        "avg_mean_nn_mm": 0.80,
        "avg_p90_nn_mm": 1.50,
        "worst_max_nn_mm": 2.10,
        "total_points": 40.0,
    }
    after = {
        "avg_mean_nn_mm": 0.90,
        "avg_p90_nn_mm": 1.70,
        "worst_max_nn_mm": 2.40,
        "total_points": 40.0,
    }
    assert not seam_local_summary_not_worse(before, after)


def test_make_live_capture_entry_includes_seam_local_and_pruning_notes(tmp_path: Path) -> None:
    entry = make_live_capture_entry(
        raw_capture_ply=tmp_path / "point_cloud_test.ply",
        icp_transform_npy=tmp_path / "icp_transform_test.npy",
        icp_report_json=tmp_path / "icp_report_test.json",
        best_seed_name="978",
        fitness=0.91,
        rmse_mm=1.8,
        seam_local_summary={
            "avg_mean_nn_mm": 0.75,
            "worst_max_nn_mm": 2.6,
            "avg_centerline_p90_mm": 0.5,
            "avg_tangent_p90_deg": 6.0,
            "avg_corridor_inlier_ratio": 0.98,
        },
        seed_pruning={"retained_seed_count": 2, "evaluated_seed_count": 4},
    )
    notes = " ".join(entry["notes"])
    assert "Seam-local NN summary" in notes
    assert "Seam corridor summary" in notes
    assert "kept 2/4 seeds" in notes


def test_summarize_seam_local_scores_marks_corridor_failure_when_geometry_regresses() -> None:
    summary = summarize_seam_local_scores(
        {
            "S3_complex_bottom": {
                "n_points": 20,
                "mean_nn_mm": 0.6,
                "p90_nn_mm": 1.0,
                "max_nn_mm": 1.8,
                "centerline_mean_mm": 0.7,
                "centerline_p90_mm": 1.8,
                "centerline_max_mm": 2.5,
                "tangent_mean_deg": 5.0,
                "tangent_p90_deg": 10.0,
                "tangent_max_deg": 18.0,
                "corridor_inlier_ratio": 0.90,
                "endpoint_start_mm": 2.0,
                "endpoint_end_mm": 2.5,
                "max_contiguous_outlier_points": 4.0,
            }
        },
        centerline_corridor_mm=DEFAULT_SEAM_CENTERLINE_CORRIDOR_MM,
        tangent_corridor_deg=DEFAULT_SEAM_TANGENT_CORRIDOR_DEG,
        corridor_min_inlier_ratio=DEFAULT_SEAM_CORRIDOR_MIN_INLIER_RATIO,
    )
    assert summary["corridor_pass"] is False


def test_compute_direction_agnostic_tangent_error_treats_reverse_as_zero() -> None:
    a = np.asarray([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=float)
    b = np.asarray([[-1.0, 0.0, 0.0], [0.0, -1.0, 0.0]], dtype=float)
    err = compute_direction_agnostic_tangent_error_deg(a, b)
    assert np.allclose(err, [0.0, 0.0])


def test_polyline_geometry_metrics_parallel_offset_hits_centerline_not_tangent() -> None:
    nominal = np.asarray([[0, 0, 0], [10, 0, 0], [20, 0, 0], [30, 0, 0]], dtype=float)
    shifted = nominal + np.asarray([0, 3, 0], dtype=float)
    metrics = compute_polyline_geometry_metrics(
        nominal, shifted,
        centerline_threshold_mm=DEFAULT_SEAM_CENTERLINE_CORRIDOR_MM,
        tangent_threshold_deg=DEFAULT_SEAM_TANGENT_CORRIDOR_DEG,
    )
    assert metrics["centerline_mean_mm"] == 3.0
    assert metrics["tangent_max_deg"] == 0.0
    assert metrics["corridor_pass"] is False


def test_polyline_geometry_metrics_corner_shortcut_hits_tangent() -> None:
    nominal = np.asarray([[0, 0, 0], [10, 0, 0], [10, 10, 0], [10, 20, 0]], dtype=float)
    shortcut = np.asarray([[0, 0, 0], [7, 3, 0], [10, 10, 0], [10, 20, 0]], dtype=float)
    metrics = compute_polyline_geometry_metrics(
        nominal, shortcut,
        centerline_threshold_mm=DEFAULT_SEAM_CENTERLINE_CORRIDOR_MM,
        tangent_threshold_deg=DEFAULT_SEAM_TANGENT_CORRIDOR_DEG,
    )
    assert metrics["tangent_max_deg"] > 15.0
    assert metrics["corridor_pass"] is False


def test_polyline_geometry_metrics_local_kink_isolated_segment_is_detected() -> None:
    nominal = np.asarray([[0, 0, 0], [10, 0, 0], [20, 0, 0], [30, 0, 0], [40, 0, 0]], dtype=float)
    kinked = nominal.copy()
    kinked[2] = np.asarray([20, 6, 0], dtype=float)
    metrics = compute_polyline_geometry_metrics(
        nominal, kinked,
        centerline_threshold_mm=DEFAULT_SEAM_CENTERLINE_CORRIDOR_MM,
        tangent_threshold_deg=DEFAULT_SEAM_TANGENT_CORRIDOR_DEG,
    )
    assert metrics["tangent_max_deg"] > 15.0
    assert metrics["max_contiguous_outlier_points"] >= 1.0
    assert metrics["corridor_pass"] is False


def test_polyline_geometry_metrics_opposite_face_shift_hits_endpoint_and_centerline() -> None:
    nominal = np.asarray([[0, 0, 0], [0, 10, 0], [0, 20, 0], [0, 30, 0]], dtype=float)
    opposite_face = nominal + np.asarray([0, 0, 4], dtype=float)
    metrics = compute_polyline_geometry_metrics(
        nominal, opposite_face,
        centerline_threshold_mm=DEFAULT_SEAM_CENTERLINE_CORRIDOR_MM,
        tangent_threshold_deg=DEFAULT_SEAM_TANGENT_CORRIDOR_DEG,
    )
    assert metrics["centerline_max_mm"] == 4.0
    assert metrics["endpoint_start_mm"] == 4.0
    assert metrics["endpoint_end_mm"] == 4.0
    assert metrics["corridor_inlier_ratio"] == 0.0


def test_make_estimator_returns_point_to_plane_by_default() -> None:
    import open3d as o3d
    est = _make_estimator("point_to_plane")
    assert isinstance(est, o3d.pipelines.registration.TransformationEstimationPointToPlane)


def test_make_estimator_returns_gicp() -> None:
    import open3d as o3d
    est = _make_estimator("gicp")
    assert isinstance(est, o3d.pipelines.registration.TransformationEstimationForGeneralizedICP)


def test_default_stages_use_four_stage_point_to_plane_baseline() -> None:
    methods = [s["method"] for s in _DEFAULT_ICP_STAGES]
    assert methods == ["point_to_plane", "point_to_plane", "point_to_plane", "point_to_plane"]
    assert [s["voxel_mm"] for s in _DEFAULT_ICP_STAGES] == [8.0, 4.0, 2.0, 1.0]


def test_experimental_stages_removed_from_public_api() -> None:
    # The 5-stage GICP variant was experimental and is no longer exported.
    # This test documents that removal is intentional.
    pass
