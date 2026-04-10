"""Tests for dts.config path rebasing and config loading."""
from pathlib import Path

import pytest

from dts.config import (
    rebase_path,
    rebase_registry_paths,
    _ORIGINAL_DATA_ROOT,
    load_config,
    reset_config,
)


def test_rebase_path_remaps_original_prefix():
    original = "/mnt/c/Users/hanmech/Desktop/DTS_image/pipeline/ref.ply"
    data_root = Path("/data/shared")
    result = rebase_path(original, data_root)
    assert result == Path("/data/shared/pipeline/ref.ply")


def test_rebase_path_leaves_unrelated_path_unchanged():
    original = "/tmp/some_other_file.ply"
    data_root = Path("/data/shared")
    result = rebase_path(original, data_root)
    assert result == Path("/tmp/some_other_file.ply")


def test_rebase_path_returns_as_is_when_data_root_is_none():
    original = "/mnt/c/Users/hanmech/Desktop/DTS_image/captures/test.ply"
    result = rebase_path(original, None)
    assert result == Path(original)


def test_rebase_registry_paths_remaps_all_path_keys():
    registry = {
        "reference_pcd": "/mnt/c/Users/hanmech/Desktop/DTS_image/pipeline/ref.ply",
        "captures": {
            "978": {
                "raw_capture_ply": "/mnt/c/Users/hanmech/Desktop/DTS_image/captures/cap.ply",
                "icp_transform_npy": "/mnt/c/Users/hanmech/Desktop/DTS_image/pipeline/T.npy",
                "notes": ["some note"],
            }
        },
    }
    data_root = Path("/opt/dts_data")
    result = rebase_registry_paths(registry, data_root)
    assert result["reference_pcd"] == "/opt/dts_data/pipeline/ref.ply"
    assert result["captures"]["978"]["raw_capture_ply"] == "/opt/dts_data/captures/cap.ply"
    assert result["captures"]["978"]["icp_transform_npy"] == "/opt/dts_data/pipeline/T.npy"


def test_rebase_registry_paths_noop_when_none():
    registry = {
        "reference_pcd": "/mnt/c/Users/hanmech/Desktop/DTS_image/pipeline/ref.ply",
        "captures": {},
    }
    result = rebase_registry_paths(registry, None)
    assert result["reference_pcd"] == "/mnt/c/Users/hanmech/Desktop/DTS_image/pipeline/ref.ply"


def test_load_config_returns_empty_for_missing_file(tmp_path):
    result = load_config(tmp_path / "nonexistent.json")
    assert result == {}


def test_load_config_reads_json(tmp_path):
    cfg_path = tmp_path / "test_config.json"
    cfg_path.write_text('{"data_root": "/tmp/test"}')
    result = load_config(cfg_path)
    assert result["data_root"] == "/tmp/test"
