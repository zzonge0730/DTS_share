import argparse
import random
import socket
import time


def build_payload(start_x, count, mode, step, jitter):
    if mode == "malformed":
        return "GARBAGE"
    if mode == "bad_header":
        return "9999,0003,1.0,2.0,3.0,0.0,0.0,0.0"
    if mode == "bad_count":
        return "1100,0003,100.0,0.0,0.0,0.0,0.0,0.0"
    if mode == "out_of_range":
        return "1100,0001,99999.0,0.0,0.0,0.0,0.0,0.0"

    parts = ["1100", f"{count:04d}"]
    x = start_x
    for i in range(count):
        if mode == "uniform":
            x = start_x + i * step
        else:
            if i == 0:
                x = start_x
            else:
                x += step + random.uniform(-jitter, jitter)
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=50001)
    ap.add_argument("--pose-count", type=int, default=7)
    ap.add_argument("--send-on-ready", action="store_true")
    ap.add_argument(
        "--mode",
        choices=["uniform", "random", "malformed", "bad_header", "bad_count", "out_of_range"],
        default="uniform",
    )
    ap.add_argument("--step", type=float, default=10.0)
    ap.add_argument("--jitter", type=float, default=2.0)
    ap.add_argument("--repeat", choices=["none", "on_ready", "interval"], default="none")
    ap.add_argument("--cooldown-ms", type=int, default=200)
    ap.add_argument("--max-repeats", type=int, default=0)
    ap.add_argument("--interval-ms", type=int, default=1000)
    args = ap.parse_args()

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((args.host, args.port))
    srv.listen(1)
    print(f"[vision] TCP listen {args.host}:{args.port}")

    conn, addr = srv.accept()
    print(f"[vision] connected {addr}")
    conn.settimeout(0.5)

    sent = False
    send_count = 0
    last_send_ts = 0.0
    repeat_mode = args.repeat
    if args.send_on_ready and repeat_mode == "none":
        repeat_mode = "on_ready"
    cooldown = max(0, args.cooldown_ms) / 1000.0
    interval = max(0, args.interval_ms) / 1000.0

    def can_send():
        nonlocal last_send_ts, send_count
        if args.max_repeats > 0 and send_count >= args.max_repeats:
            return False
        now = time.time()
        if now - last_send_ts < cooldown:
            return False
        last_send_ts = now
        send_count += 1
        return True

    def send_payload():
        payload = build_payload(100.0, args.pose_count, args.mode, args.step, args.jitter)
        conn.sendall(payload.encode("ascii"))
        print(f"[vision] sent payload cnt={args.pose_count} mode={args.mode} repeats={send_count}")

    while True:
        try:
            data = conn.recv(4096)
        except socket.timeout:
            data = b""

        if data:
            msg = data.decode("ascii", errors="ignore").strip()
            print(f"[vision] recv: {msg}")
            if "READY" in msg:
                if repeat_mode == "on_ready":
                    if can_send():
                        send_payload()
                elif args.send_on_ready and not sent:
                    if can_send():
                        send_payload()
                        sent = True
        else:
            if repeat_mode == "interval":
                if (time.time() - last_send_ts >= interval) and can_send():
                    send_payload()
            elif repeat_mode == "none" and not args.send_on_ready and not sent:
                if can_send():
                    send_payload()
                    sent = True
            time.sleep(0.1)


if __name__ == "__main__":
    main()
