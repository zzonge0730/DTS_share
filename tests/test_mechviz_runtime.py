from pathlib import Path
import os
import sys

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from mechviz_runtime import (
    build_project_open_command,
    build_service_start_command,
    build_service_stop_command,
    build_trigger_simulation_command,
    parse_service_start_report,
    default_mechviz_runtime_config,
    load_mechviz_runtime_config,
    parse_service_start_output,
    resolve_mechmind_python_exe,
    save_mechviz_runtime_config,
    trigger_mechviz_execution,
)


def test_default_mechviz_runtime_config_has_expected_keys() -> None:
    config = default_mechviz_runtime_config()
    assert "communication_component_root" in config
    assert "project_dir" in config
    assert config["motion_type"] == "L"


def test_load_and_save_mechviz_runtime_config_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "mechviz_runtime_config.json"
    config = default_mechviz_runtime_config()
    config["service_name"] = "Test Service"
    save_mechviz_runtime_config(config, path)
    loaded = load_mechviz_runtime_config(path)
    assert loaded["service_name"] == "Test Service"


def test_resolve_mechmind_python_exe_uses_comm_root() -> None:
    config = default_mechviz_runtime_config()
    config["communication_component_root"] = r"C:\Mech-Mind\Communication Component"
    assert resolve_mechmind_python_exe(config) == r"C:\Mech-Mind\Communication Component\python\python.exe"


def test_build_service_start_command_includes_expected_args() -> None:
    config = default_mechviz_runtime_config()
    cmd = build_service_start_command(
        windows_python_exe=r"C:\Mech-Mind\CC\python\python.exe",
        windows_launcher_script=r"\\wsl.localhost\Ubuntu-22.04\home\hanmech\DTS\scripts\start_mechviz_service.ps1",
        windows_service_script=r"\\wsl.localhost\Ubuntu-22.04\home\hanmech\DTS\scripts\viz_outer_move_service.py",
        windows_pose_csv_path=r"\\wsl.localhost\Ubuntu-22.04\home\hanmech\DTS\data\U1_pose.csv",
        config=config,
    )
    joined = " ".join(cmd)
    assert cmd[0] == "powershell.exe"
    assert "-Command" in joined
    assert "-NoProfile" in joined
    assert "viz_outer_move_service.py" in joined
    assert "DTS Weld Seam Outer Move" in joined
    assert "Start-Process" in joined


def test_build_service_stop_command_targets_pid() -> None:
    assert build_service_stop_command(1234) == ["taskkill.exe", "/PID", "1234", "/T", "/F"]


def test_build_project_open_command_uses_powershell_start_process() -> None:
    cmd = build_project_open_command(r"C:\Users\hanmech\Desktop\DTS_image\Mech-Viz-dCNwPT\Mech-Viz-dCNwPT.viz")
    assert cmd[0] == "powershell.exe"
    assert "Start-Process" in " ".join(cmd)


def test_parse_service_start_output_extracts_pid() -> None:
    assert parse_service_start_output("PID=4321\n") == 4321


def test_parse_service_start_report_extracts_pid_logs_and_alive() -> None:
    text = "STDOUT_LOG=C:\\Temp\\out.log\nSTDERR_LOG=C:\\Temp\\err.log\nALIVE=1\nPID=4321\n"
    report = parse_service_start_report(text)
    assert report["pid"] == 4321
    assert report["stdout_log"] == r"C:\Temp\out.log"
    assert report["stderr_log"] == r"C:\Temp\err.log"
    assert report["alive"] is True


def test_build_trigger_simulation_command_uses_powershell() -> None:
    config = default_mechviz_runtime_config()
    cmd = build_trigger_simulation_command(config)
    assert cmd[0] == "powershell.exe"
    joined = " ".join(cmd)
    assert "HubCaller" in joined
    assert "executor" in joined
    assert "function': 'run" in joined or "function'': ''run" in joined


def test_build_trigger_simulation_command_raises_on_empty_root() -> None:
    config = default_mechviz_runtime_config()
    config["communication_component_root"] = ""
    import pytest
    with pytest.raises(ValueError, match="empty"):
        build_trigger_simulation_command(config)


def test_trigger_mechviz_execution_returns_not_triggered_on_empty_root() -> None:
    config = default_mechviz_runtime_config()
    config["communication_component_root"] = ""
    result = trigger_mechviz_execution(config)
    assert result["triggered"] is False
    assert "empty" in result["reason"]
