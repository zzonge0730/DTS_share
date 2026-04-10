"""Smoke tests: verify dts/ package imports work without scripts/ on sys.path."""
import subprocess
import sys
import textwrap

import pytest


def test_dts_pose_imports_standalone():
    """dts.pose must import without scripts/ on sys.path."""
    code = textwrap.dedent("""\
        import sys
        # Remove any scripts/ entries from sys.path
        sys.path = [p for p in sys.path if 'scripts' not in p]
        from dts.pose import Pose6D, resample_uniform, compute_tangent_vectors
        from dts.pose import build_poses, estimate_surface_normal
        from dts.pose import save_pose_csv, format_1100, save_1100
        print("OK")
    """)
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "OK" in result.stdout


def test_dts_seam_imports_standalone():
    """dts.seam must import without scripts/ on sys.path."""
    code = textwrap.dedent("""\
        import sys
        sys.path = [p for p in sys.path if 'scripts' not in p]
        from dts.seam import snap_to_surface, apply_snap_strategy, resolve_snap_mode
        from dts.seam import score_nn_distance, estimate_local_normals
        print("OK")
    """)
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "OK" in result.stdout


def test_dts_icp_imports_standalone():
    """dts.icp must import without scripts/ on sys.path."""
    code = textwrap.dedent("""\
        import sys
        sys.path = [p for p in sys.path if 'scripts' not in p]
        from dts.icp import (
            run_icp_stages_from_init, choose_best_result,
            compute_polyline_geometry_metrics,
            summarize_seam_local_scores,
        )
        print("OK")
    """)
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "OK" in result.stdout


def test_dts_transforms_imports_standalone():
    """dts.transforms must import without scripts/ on sys.path."""
    code = textwrap.dedent("""\
        import sys
        sys.path = [p for p in sys.path if 'scripts' not in p]
        from dts.transforms import transform_points, rotation_matrix_to_euler_zyx
        print("OK")
    """)
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "OK" in result.stdout
