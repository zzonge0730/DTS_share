import os
import sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from mecheye_capture import default_camera_config, load_camera_config, save_camera_config


def test_default_camera_config_contains_expected_keys() -> None:
    config = default_camera_config()
    assert "camera_ip" in config
    assert "captures_dir" in config
    assert config["default_capture_tag"] == "gui"


def test_camera_config_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "camera_config.json"
    config = default_camera_config()
    config["camera_ip"] = "192.168.10.20"
    save_camera_config(config, path)
    loaded = load_camera_config(path)
    assert loaded["camera_ip"] == "192.168.10.20"
