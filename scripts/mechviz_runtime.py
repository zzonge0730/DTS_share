#!/usr/bin/env python3
"""
mechviz_runtime.py - Helper for launching/stopping Mech-Viz OuterMoveService
from WSL-driven tooling.

This helper intentionally manages only the adapter service process. Launching
the actual Mech-Viz project remains an external/manual step for now.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path, PureWindowsPath
from typing import Any


import _bootstrap  # noqa: F401 — repo root + scripts/ on sys.path
from dts.config import REPO_ROOT, DEFAULT_MECHVIZ_CONFIG


def _win_to_wsl_path(win_path: str) -> str:
    """Convert a Windows path like C:\\foo\\bar to /mnt/c/foo/bar for WSL exec."""
    p = win_path.replace("\\", "/")
    # Handle drive letter: C:/... -> /mnt/c/...
    if len(p) >= 2 and p[1] == ":":
        drive = p[0].lower()
        return f"/mnt/{drive}{p[2:]}"
    return p

WINDOWS_INTEROP_ERROR_MARKERS = (
    "UtilBindVsockAnyPort",
    "socket failed 1",
)


def default_mechviz_runtime_config() -> dict[str, Any]:
    return {
        "communication_component_root": r"C:\Mech-Mind\Mech-Vision & Mech-Viz-2.1.2\Communication Component",
        "project_dir": r"C:\Users\hanmech\Desktop\DTS_image\Mech-Viz-dCNwPT",
        "service_name": "DTS Weld Seam Outer Move",
        "motion_type": "L",
        "velocity": 0.15,
        "acceleration": 0.15,
        "blend_radius": 0.01,
    }


def detect_windows_interop_error(text: str) -> str | None:
    for marker in WINDOWS_INTEROP_ERROR_MARKERS:
        if marker in text:
            return (
                "WSL에서 Windows 프로그램 호출이 현재 실패하고 있습니다. "
                "Windows PowerShell에서 'wsl --shutdown' 실행 후 WSL을 다시 열고 재시도해 주세요."
            )
    return None


def load_mechviz_runtime_config(path: Path = DEFAULT_MECHVIZ_CONFIG) -> dict[str, Any]:
    config = default_mechviz_runtime_config()
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            loaded = json.load(f)
        config.update(loaded)
    return config


def save_mechviz_runtime_config(
    config: dict[str, Any], path: Path = DEFAULT_MECHVIZ_CONFIG
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    return path


def resolve_mechmind_python_exe(config: dict[str, Any]) -> str:
    root = str(config.get("communication_component_root", "")).strip()
    if not root:
        raise ValueError("communication_component_root is empty")
    return str(PureWindowsPath(root) / "python" / "python.exe")


def resolve_project_dir(config: dict[str, Any]) -> str:
    return str(config.get("project_dir", "")).strip()


def build_service_start_command(
    *,
    windows_python_exe: str,
    windows_launcher_script: str,
    windows_service_script: str,
    windows_pose_csv_path: str,
    robot_base: tuple[float, float, float] = (1.3, -0.5, 0.0),
    config: dict[str, Any],
) -> list[str]:
    service_name = str(config.get("service_name") or "DTS Weld Seam Outer Move")
    motion_type = str(config.get("motion_type") or "L")
    velocity = float(config.get("velocity", 0.15))
    acceleration = float(config.get("acceleration", 0.15))
    blend_radius = float(config.get("blend_radius", 0.01))
    cc_root = str(config.get("communication_component_root", "")).strip()

    # Build the inline PowerShell command — avoids slow UNC path reads for .ps1 files.
    def esc(s: str) -> str:
        return s.replace("'", "''")

    set_env = f"$env:MECH_CC_ROOT = '{esc(cc_root)}'; " if cc_root else ""
    arg_parts = [
        f'\'"{esc(windows_service_script)}"\'',
        "'--pose-csv'", f'\'"{esc(windows_pose_csv_path)}"\'',
        "'--robot-base'", f"'{robot_base[0]}'", f"'{robot_base[1]}'", f"'{robot_base[2]}'",
        "'--service-name'", f'\'"{esc(service_name)}"\'',
        "'--motion-type'", f"'{motion_type}'",
        "'--velocity'", f"'{velocity}'",
        "'--acceleration'", f"'{acceleration}'",
        "'--blend-radius'", f"'{blend_radius}'",
    ]
    arg_list_ps = ", ".join(arg_parts)

    ps_script = (
        f"{set_env}"
        f"$stdoutLog = Join-Path $env:TEMP ('dts_mechviz_service_' + [guid]::NewGuid().ToString() + '.out.log'); "
        f"$stderrLog = Join-Path $env:TEMP ('dts_mechviz_service_' + [guid]::NewGuid().ToString() + '.err.log'); "
        f"$p = Start-Process -FilePath '{esc(windows_python_exe)}' "
        f"-ArgumentList @({arg_list_ps}) "
        f"-PassThru -WindowStyle Hidden "
        f"-RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog; "
        f"Start-Sleep -Milliseconds 2000; "
        f"$alive = $null -ne (Get-Process -Id $p.Id -ErrorAction SilentlyContinue); "
        f"Write-Output ('STDOUT_LOG=' + $stdoutLog); "
        f"Write-Output ('STDERR_LOG=' + $stderrLog); "
        f"Write-Output ('ALIVE=' + $(if ($alive) {{ '1' }} else {{ '0' }})); "
        f"if ($alive) {{ Write-Output ('PID=' + $p.Id) }} "
        f"else {{ if (Test-Path $stderrLog) {{ Get-Content $stderrLog }} }}"
    )
    return [
        "powershell.exe", "-ExecutionPolicy", "Bypass",
        "-NoProfile", "-NonInteractive",
        "-Command", ps_script,
    ]


def build_service_stop_command(pid: int) -> list[str]:
    return ["taskkill.exe", "/PID", str(pid), "/T", "/F"]


def build_pid_probe_command(pid: int) -> list[str]:
    command = (
        f"$p = Get-Process -Id {pid} -ErrorAction SilentlyContinue; "
        "if ($null -ne $p) { Write-Output 'ALIVE=1' } else { Write-Output 'ALIVE=0' }"
    )
    return ["powershell.exe", "-ExecutionPolicy", "Bypass", "-Command", command]


def build_project_open_command(windows_target_path: str) -> list[str]:
    target_escaped = windows_target_path.replace("'", "''")
    command = f"Start-Process -FilePath '{target_escaped}'"
    return ["powershell.exe", "-ExecutionPolicy", "Bypass", "-Command", command]


def parse_service_start_output(text: str) -> int:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("PID="):
            return int(line.split("=", 1)[1].strip())
    raise ValueError(f"Could not find PID in output: {text!r}")


def parse_service_start_report(text: str) -> dict[str, Any]:
    report: dict[str, Any] = {
        "pid": None,
        "stdout_log": "",
        "stderr_log": "",
        "alive": None,
    }
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("PID="):
            report["pid"] = int(line.split("=", 1)[1].strip())
        elif line.startswith("STDOUT_LOG="):
            report["stdout_log"] = line.split("=", 1)[1].strip()
        elif line.startswith("STDERR_LOG="):
            report["stderr_log"] = line.split("=", 1)[1].strip()
        elif line.startswith("ALIVE="):
            report["alive"] = line.split("=", 1)[1].strip() == "1"
    return report


def probe_windows_pid(pid: int, timeout: int = 10) -> dict[str, Any]:
    try:
        proc = subprocess.run(build_pid_probe_command(pid), capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {
            "pid": pid,
            "alive": None,
            "interop_error": f"PID probe timed out after {timeout}s",
            "raw_output": "",
        }
    stdout = proc.stdout.decode("utf-8", errors="replace") if proc.stdout else ""
    stderr = proc.stderr.decode("utf-8", errors="replace") if proc.stderr else ""
    combined = stdout + ("\n" + stderr if stderr else "")
    interop_msg = detect_windows_interop_error(combined)
    if interop_msg:
        return {
            "pid": pid,
            "alive": None,
            "interop_error": interop_msg,
            "raw_output": combined,
        }
    alive = "ALIVE=1" in combined
    return {
        "pid": pid,
        "alive": alive,
        "interop_error": None,
        "raw_output": combined,
    }


def start_outer_move_service(
    *,
    windows_launcher_script: str,
    windows_service_script: str,
    windows_pose_csv_path: str,
    config: dict[str, Any],
    robot_base: tuple[float, float, float] = (1.3, -0.5, 0.0),
) -> dict[str, Any]:
    """Start the outer-move service by launching Windows Python directly.

    Uses subprocess.Popen (no PowerShell) to avoid WSL↔PowerShell pipe hangs.
    The service reads pose.csv directly and converts internally.
    """
    windows_python_exe = resolve_mechmind_python_exe(config)
    service_name = str(config.get("service_name") or "DTS Weld Seam Outer Move")
    motion_type = str(config.get("motion_type") or "L")
    velocity = str(float(config.get("velocity", 0.15)))
    acceleration = str(float(config.get("acceleration", 0.15)))
    blend_radius = str(float(config.get("blend_radius", 0.01)))
    cc_root = str(config.get("communication_component_root", "")).strip()

    # The executable must be a WSL-resolvable path (/mnt/c/...) for Popen,
    # but arguments stay as Windows paths — the Windows Python process reads them.
    wsl_python_exe = _win_to_wsl_path(windows_python_exe)
    cmd = [
        wsl_python_exe,
        windows_service_script,
        "--pose-csv", windows_pose_csv_path,
        "--robot-base", str(robot_base[0]), str(robot_base[1]), str(robot_base[2]),
        "--service-name", service_name,
        "--motion-type", motion_type,
        "--velocity", velocity,
        "--acceleration", acceleration,
        "--blend-radius", blend_radius,
    ]

    # Set MECH_CC_ROOT so the service can find Mech-Mind SDK libs.
    env = os.environ.copy()
    if cc_root:
        env["MECH_CC_ROOT"] = cc_root

    # Redirect stdout/stderr to temp files in Windows %TEMP%.
    win_temp = Path("/mnt/c/Users") / os.environ.get("USER", "hanmech") / "AppData/Local/Temp"
    if not win_temp.exists():
        win_temp = Path(tempfile.gettempdir())

    import uuid
    stdout_log = win_temp / f"dts_mechviz_service_{uuid.uuid4()}.out.log"
    stderr_log = win_temp / f"dts_mechviz_service_{uuid.uuid4()}.err.log"

    try:
        f_out = open(stdout_log, "w")
        f_err = open(stderr_log, "w")
    except OSError as exc:
        raise RuntimeError(f"Cannot create log files in {win_temp}: {exc}") from exc

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=f_out,
            stderr=f_err,
            env=env,
            start_new_session=True,
        )
    except OSError as exc:
        f_out.close()
        f_err.close()
        interop_msg = detect_windows_interop_error(str(exc))
        if interop_msg:
            raise RuntimeError(f"{interop_msg}\n{exc}") from exc
        raise RuntimeError(f"Failed to launch service process: {exc}") from exc

    # Give the service time to start and register with the hub.
    time.sleep(3)

    alive = proc.poll() is None
    f_out.close()
    f_err.close()

    if not alive:
        err_content = ""
        try:
            err_content = stderr_log.read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass
        raise RuntimeError(
            f"Service process exited immediately (rc={proc.returncode}):\n{err_content}"
        )

    return {
        "pid": proc.pid,
        "python_exe": windows_python_exe,
        "pose_csv_path": windows_pose_csv_path,
        "project_dir": resolve_project_dir(config),
        "service_name": service_name,
        "stdout_log": str(stdout_log),
        "stderr_log": str(stderr_log),
        "raw_output": f"PID={proc.pid} ALIVE=1",
    }


def stop_outer_move_service(pid: int) -> dict[str, Any]:
    try:
        proc = subprocess.run(build_service_stop_command(pid), capture_output=True, timeout=10)
    except subprocess.TimeoutExpired as exc:
        return {
            "pid": pid,
            "returncode": None,
            "raw_output": "",
            "stopped": False,
            "interop_error": "Mech-Viz 서비스 중지가 10초 내에 완료되지 않았습니다.",
        }
    stdout = proc.stdout.decode("utf-8", errors="replace") if proc.stdout else ""
    stderr = proc.stderr.decode("utf-8", errors="replace") if proc.stderr else ""
    combined = stdout + ("\n" + stderr if stderr else "")
    interop_msg = detect_windows_interop_error(combined)
    return {
        "pid": pid,
        "returncode": proc.returncode,
        "raw_output": combined,
        "stopped": proc.returncode == 0,
        "interop_error": interop_msg,
    }


def open_mechviz_project(windows_target_path: str) -> dict[str, Any]:
    try:
        proc = subprocess.run(build_project_open_command(windows_target_path), capture_output=True, timeout=15)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            "Mech-Viz 프로젝트 열기가 15초 내에 완료되지 않았습니다."
        ) from exc
    stdout = proc.stdout.decode("utf-8", errors="replace") if proc.stdout else ""
    stderr = proc.stderr.decode("utf-8", errors="replace") if proc.stderr else ""
    combined = stdout + ("\n" + stderr if stderr else "")
    if proc.returncode != 0:
        interop_msg = detect_windows_interop_error(combined)
        if interop_msg:
            raise RuntimeError(f"{interop_msg}\n{combined}")
        raise RuntimeError(f"Failed to open Mech-Viz target: {combined}")
    return {
        "target_path": windows_target_path,
        "returncode": proc.returncode,
        "raw_output": combined,
    }


def build_trigger_simulation_command(config: dict[str, Any]) -> list[str]:
    """Build PowerShell command to trigger Mech-Viz execution via Communication Component."""
    cc_root = str(config.get("communication_component_root", "")).strip()
    if not cc_root:
        raise ValueError("communication_component_root is empty")

    python_exe = str(PureWindowsPath(cc_root) / "python" / "python.exe")
    project_dir = resolve_project_dir(config)

    # Write a temporary Python script to avoid & and quote issues in PowerShell
    # when cc_root contains special characters (e.g. "Mech-Vision & Mech-Viz").
    # Communication Component 2.1.x exposes generic HubCaller.call() reliably,
    # while HubCaller.start_viz() is not available in this environment.
    trigger_py_lines = [
        "import sys, os",
        f"cc_root = {cc_root!r}",
        f"project_dir = {project_dir!r}",
        r"sys.path.insert(0, os.path.join(cc_root, 'python', 'Lib', 'site-packages'))",
        r"sys.path.insert(0, os.path.join(cc_root, 'src'))",
        "from unified_service.caller import HubCaller",
        "hub = HubCaller('127.0.0.1:5308')",
        "msg = {'function': 'run', 'simulate': True}",
        "if project_dir: msg['project_dir'] = project_dir",
        "result = hub.call('forward', {'name': 'executor', 'message': msg})",
        "print(result.decode() if hasattr(result, 'decode') else result)",
        "print('TRIGGER_OK')",
    ]
    trigger_py_content = "\n".join(trigger_py_lines)

    # Use %TEMP% for the trigger script, and powershell to write + execute + clean up.
    py_escaped = python_exe.replace("'", "''")
    content_escaped = trigger_py_content.replace("'", "''")

    command = (
        "$tmp_py = Join-Path $env:TEMP 'dts_trigger_script.py'; "
        "$tmp_out = Join-Path $env:TEMP 'dts_trigger_out.txt'; "
        f"Set-Content -Path $tmp_py -Value '{content_escaped}' -Encoding UTF8; "
        f"$p = Start-Process -FilePath '{py_escaped}' "
        f"-ArgumentList @($tmp_py) "
        f"-Wait -PassThru -NoNewWindow -RedirectStandardOutput $tmp_out; "
        f"Get-Content $tmp_out; "
        f"Remove-Item $tmp_py -ErrorAction SilentlyContinue; "
        f"Remove-Item $tmp_out -ErrorAction SilentlyContinue; "
        f"Write-Output ('EXIT=' + $p.ExitCode)"
    )
    return ["powershell.exe", "-ExecutionPolicy", "Bypass", "-Command", command]


def trigger_mechviz_execution(config: dict[str, Any]) -> dict[str, Any]:
    """Attempt to trigger Mech-Viz simulation via Communication Component hub.

    Returns a result dict with 'triggered' bool.  Best-effort: if the API
    is not available or Mech-Viz is not running, returns triggered=False
    without raising.
    """
    try:
        cmd = build_trigger_simulation_command(config)
    except ValueError as exc:
        return {"triggered": False, "reason": str(exc), "raw_output": ""}

    proc = subprocess.run(cmd, capture_output=True, timeout=15)
    stdout = proc.stdout.decode("utf-8", errors="replace") if proc.stdout else ""
    stderr = proc.stderr.decode("utf-8", errors="replace") if proc.stderr else ""
    combined = stdout + ("\n" + stderr if stderr else "")
    interop_msg = detect_windows_interop_error(combined)
    if interop_msg:
        return {
            "triggered": False,
            "reason": "windows_interop_unavailable",
            "returncode": proc.returncode,
            "raw_output": combined,
            "interop_error": interop_msg,
        }
    triggered = "TRIGGER_OK" in combined and proc.returncode == 0
    return {
        "triggered": triggered,
        "reason": "ok" if triggered else "hub_call_failed",
        "returncode": proc.returncode,
        "raw_output": combined,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Mech-Viz OuterMoveService launcher helper")
    sub = parser.add_subparsers(dest="cmd", required=True)

    start = sub.add_parser("start")
    start.add_argument("--pose-csv", required=True, help="Windows path to pose.csv")
    start.add_argument("--service-script", required=True, help="Windows path to viz_outer_move_service.py")
    start.add_argument("--config", type=Path, default=DEFAULT_MECHVIZ_CONFIG)

    stop = sub.add_parser("stop")
    stop.add_argument("--pid", type=int, required=True)

    open_cmd = sub.add_parser("open-project")
    open_cmd.add_argument("--target", required=True, help="Windows path to .viz file or project folder")

    args = parser.parse_args()
    if args.cmd == "start":
        config = load_mechviz_runtime_config(args.config)
        launcher = str(PureWindowsPath(args.service_script).parent / "start_mechviz_service.ps1")
        result = start_outer_move_service(
            windows_launcher_script=launcher,
            windows_service_script=args.service_script,
            windows_pose_csv_path=args.pose_csv,
            config=config,
        )
        print(json.dumps(result, indent=2))
    elif args.cmd == "open-project":
        print(json.dumps(open_mechviz_project(args.target), indent=2))
    else:
        print(json.dumps(stop_outer_move_service(args.pid), indent=2))


if __name__ == "__main__":
    main()
