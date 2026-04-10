import argparse
import math
import random
import socket
import sys
import time
from pathlib import Path
from typing import List

_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from transforms import quat_to_euler_zyx


def _safe_int(value: str, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value: str, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def build_fallback_payload(count: int, step: float = 10.0) -> str:
    parts = ["1100", f"{count:04d}"]
    for i in range(count):
        x = 100.0 + i * step
        y = 0.0
        z = 0.0
        rx = 0.0
        ry = 0.0
        rz = 0.0
        parts.extend(
            [
                f"{x:.3f}",
                f"{y:.3f}",
                f"{z:.3f}",
                f"{rx:.3f}",
                f"{ry:.3f}",
                f"{rz:.3f}",
            ]
        )
    return ",".join(parts)


def quat_to_euler(qw: float, qx: float, qy: float, qz: float, convention: str = "ZYX") -> List[float]:
    if convention != "ZYX":
        raise ValueError(f"unsupported Euler convention: {convention}")
    rx, ry, rz = quat_to_euler_zyx(qw, qx, qy, qz)
    return [rx, ry, rz]


def normalize_to_1100(
    raw: str,
    default_count: int,
    allow_fallback: bool = True,
    euler_convention: str = "ZYX",
) -> str:
    # In production bridge mode (Mech connected), avoid synthesizing robot poses on parse failure.
    # Returning an empty payload forces a fail-safe path handled by the caller.
    msg = raw.strip().strip(",")
    if not msg:
        return build_fallback_payload(default_count) if allow_fallback else ""

    parts = [p.strip() for p in msg.split(",") if p.strip() != ""]
    if len(parts) < 2:
        return build_fallback_payload(default_count) if allow_fallback else ""

    # Case A: already DTS contract
    if parts[0] == "1100":
        cnt = _safe_int(parts[1], 0)
        values = parts[2:]
        if cnt <= 0:
            cnt = len(values) // 6
        need = cnt * 6
        values = values[:need]
        if len(values) < need:
            # If malformed, fallback for safety.
            return build_fallback_payload(default_count) if allow_fallback else ""
        return ",".join(["1100", f"{cnt:04d}", *values])

    # Case B: 102 response with 1100 status (Vision result)
    # Typical shape: 102,1100,<pose_type>,<count>,<pose values...>
    # Case C: 205 response with 2100 status (Viz path)
    # Typical shape: 205,2100,<pose_type>,<count>,<pose values...>
    is_vision = parts[0] == "102" and parts[1] == "1100"
    is_viz = parts[0] == "205" and parts[1] == "2100"
    if is_vision or is_viz:
        if len(parts) < 4:
            return build_fallback_payload(default_count) if allow_fallback else ""

        pose_type = _safe_int(parts[2], 2)
        count = _safe_int(parts[3], 0)
        values = parts[4:]
        if count <= 0:
            count = default_count

        # Some integrations return:
        # - 6 fields/pose: x,y,z,rx,ry,rz
        # - 7 fields/pose: x,y,z,qw,qx,qy,qz
        # - 8 fields/pose: x,y,z,rx,ry,rz,label,tool
        stride = 8 if len(values) >= count * 8 else (7 if len(values) >= count * 7 else 6)
        normalized: List[str] = []
        for i in range(count):
            base = i * stride
            if base + 5 >= len(values):
                break
            x = _safe_float(values[base + 0])
            y = _safe_float(values[base + 1])
            z = _safe_float(values[base + 2])
            if stride == 7:
                qw = _safe_float(values[base + 3])
                qx = _safe_float(values[base + 4])
                qy = _safe_float(values[base + 5])
                qz = _safe_float(values[base + 6])
                try:
                    rx, ry, rz = quat_to_euler(qw, qx, qy, qz, convention=euler_convention)
                except Exception:
                    break
            else:
                rx = _safe_float(values[base + 3])
                ry = _safe_float(values[base + 4])
                rz = _safe_float(values[base + 5])
            normalized.extend(
                [
                    f"{x:.3f}",
                    f"{y:.3f}",
                    f"{z:.3f}",
                    f"{rx:.3f}",
                    f"{ry:.3f}",
                    f"{rz:.3f}",
                ]
            )

        count = len(normalized) // 6
        if count <= 0:
            return build_fallback_payload(default_count) if allow_fallback else ""
        return ",".join(["1100", f"{count:04d}", *normalized])

    return build_fallback_payload(default_count) if allow_fallback else ""


def recv_line(sock: socket.socket, timeout: float) -> str:
    sock.settimeout(timeout)
    chunks: List[bytes] = []
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break
        chunks.append(chunk)
        if b"\n" in chunk or b"\r" in chunk:
            break
        if len(chunk) < 4096:
            break
    return b"".join(chunks).decode("ascii", errors="ignore").strip()


def mech_query(
    host: str,
    port: int,
    timeout: float,
    query_mode: str,
    trigger_recipe: int,
    pose_type: int,
    viz_use_branch: bool,
    viz_branch_name: int,
    viz_branch_exit: int,
    viz_use_index: bool,
    viz_index_skill: int,
    viz_index_count: int,
) -> str:
    # Minimal query sequence:
    # - vision mode: 101 trigger -> 102 result
    # - viz205 mode: 205 path query
    # - viz_full mode: 201 -> (203) -> (204) -> 205 -> 202
    with socket.create_connection((host, port), timeout=timeout) as s:
        s.settimeout(timeout)
        if query_mode == "vision":
            cmd_101 = f"101,1,{trigger_recipe},{pose_type},0,0,0,0,0,0,\n"
            s.sendall(cmd_101.encode("ascii"))
            _ = recv_line(s, timeout)

            cmd_102 = "102,1,\n"
            s.sendall(cmd_102.encode("ascii"))
            return recv_line(s, timeout)

        if query_mode == "viz205":
            cmd_205 = f"205,{pose_type},\n"
            s.sendall(cmd_205.encode("ascii"))
            return recv_line(s, timeout)

        if query_mode == "viz_full":
            # 201 expects pose type 1 (JPS) and six joint values.
            cmd_201 = "201,1,0,0,0,0,0,0,\n"
            s.sendall(cmd_201.encode("ascii"))
            _ = recv_line(s, timeout)

            if viz_use_branch:
                cmd_203 = f"203,{viz_branch_name},{viz_branch_exit},\n"
                s.sendall(cmd_203.encode("ascii"))
                _ = recv_line(s, timeout)

            if viz_use_index:
                cmd_204 = f"204,{viz_index_skill},{viz_index_count},\n"
                s.sendall(cmd_204.encode("ascii"))
                _ = recv_line(s, timeout)

            cmd_205 = f"205,{pose_type},\n"
            s.sendall(cmd_205.encode("ascii"))
            raw_205 = recv_line(s, timeout)

            # Best-effort stop to close viz cycle.
            try:
                cmd_202 = "202,\n"
                s.sendall(cmd_202.encode("ascii"))
                _ = recv_line(s, timeout)
            except Exception:
                pass

            return raw_205

        raise ValueError(f"unsupported query_mode: {query_mode}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--listen-host", default="0.0.0.0")
    ap.add_argument("--listen-port", type=int, default=50001)
    ap.add_argument("--mech-host", default="")
    ap.add_argument("--mech-port", type=int, default=8000)
    ap.add_argument("--mech-timeout", type=float, default=1.5)
    ap.add_argument("--query-mode", choices=["vision", "viz205", "viz_full"], default="vision")
    ap.add_argument("--trigger-recipe", type=int, default=1)
    ap.add_argument("--pose-type", type=int, choices=[1, 2], default=2)
    ap.add_argument("--viz-use-branch", action="store_true")
    ap.add_argument("--viz-branch-name", type=int, default=1)
    ap.add_argument("--viz-branch-exit", type=int, default=1)
    ap.add_argument("--viz-use-index", action="store_true")
    ap.add_argument("--viz-index-skill", type=int, default=1)
    ap.add_argument("--viz-index-count", type=int, default=1)
    ap.add_argument("--euler-convention", choices=["ZYX"], default="ZYX")
    ap.add_argument("--fallback-count", type=int, default=7)
    ap.add_argument("--fallback-step", type=float, default=10.0)
    ap.add_argument("--payload-file", default="",
                    help="File containing 1100 payload to send instead of fallback/mech")
    ap.add_argument("--send-on-any-msg", action="store_true")
    args = ap.parse_args()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((args.listen_host, args.listen_port))
    server.listen(1)
    print(f"[adapter] listen {args.listen_host}:{args.listen_port}")
    if args.mech_host:
        print(f"[adapter] mech target {args.mech_host}:{args.mech_port}")
    else:
        print("[adapter] mech target disabled -> fallback payload mode")

    conn, addr = server.accept()
    conn.settimeout(0.5)
    print(f"[adapter] DTS connected {addr}")

    while True:
        try:
            data = conn.recv(4096)
        except socket.timeout:
            continue

        if not data:
            print("[adapter] DTS disconnected")
            break

        msg = data.decode("ascii", errors="ignore").strip()
        print(f"[adapter] recv: {msg}")
        should_run = "READY" in msg or args.send_on_any_msg
        if not should_run:
            continue

        payload = ""
        if args.payload_file:
            try:
                with open(args.payload_file, "r", encoding="utf-8") as pf:
                    payload_raw = pf.read().strip()
                payload = normalize_to_1100(
                    payload_raw,
                    args.fallback_count,
                    allow_fallback=False,
                    euler_convention=args.euler_convention,
                )
                if not payload or not payload.startswith("1100,"):
                    raise ValueError("invalid payload file format")
                print(f"[adapter] loaded payload from {args.payload_file} ({len(payload)} chars)")
            except Exception as ex:
                print(f"[adapter] payload file read failed: {ex}")
                conn.close()
                break
        elif args.mech_host:
            try:
                raw = mech_query(
                    args.mech_host,
                    args.mech_port,
                    args.mech_timeout,
                    args.query_mode,
                    args.trigger_recipe,
                    args.pose_type,
                    args.viz_use_branch,
                    args.viz_branch_name,
                    args.viz_branch_exit,
                    args.viz_use_index,
                    args.viz_index_skill,
                    args.viz_index_count,
                )
                print(f"[adapter] mech raw: {raw}")
                payload = normalize_to_1100(
                    raw,
                    args.fallback_count,
                    allow_fallback=False,
                    euler_convention=args.euler_convention,
                )
                if not payload:
                    # Fail-safe: do not emit fabricated poses when Mech response is unknown/malformed.
                    print("[adapter] fail-safe: invalid mech payload, closing DTS connection")
                    conn.close()
                    break
            except Exception as ex:
                print(f"[adapter] mech query failed: {ex}")
                # Fail-safe: query failures should stop pose streaming, not generate dummy trajectories.
                conn.close()
                break
        else:
            jitter = random.uniform(-0.2, 0.2)
            payload = build_fallback_payload(args.fallback_count, args.fallback_step + jitter)

        # Newline helps line-oriented peers delimit payloads consistently.
        conn.sendall((payload + "\n").encode("ascii"))
        print(f"[adapter] sent: {payload[:120]}...")
        time.sleep(0.02)


if __name__ == "__main__":
    main()
