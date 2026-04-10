import argparse
import socket
import time
import select


def try_parse_comma(payload):
    try:
        parts = payload.split(",")
        code = parts[0]
        cnt = int(parts[1])
        values = parts[2:]
        pose_fields = 6
        expected = cnt * pose_fields
        ok = len(values) >= expected
        return {
            "ok": ok,
            "code": code,
            "cnt": cnt,
            "fields": len(values),
            "expected_fields": expected,
        }
    except Exception:
        return None


def try_parse_fixed(payload):
    # naive fixed-width probe (header 4 + count 4 then 6*? values width 10)
    if len(payload) < 8:
        return None
    code = payload[0:4]
    try:
        cnt = int(payload[5:9])
    except Exception:
        return None
    return {"code": code, "cnt": cnt}


def try_parse_status(payload):
    parts = payload.split(",")
    if not parts:
        return None
    code = parts[0]
    if code not in ("2002", "1004", "2100"):
        return None
    if code == "1004":
        if len(parts) < 3:
            return {"code": code, "ok": False, "reason": None, "ts": None}
        return {"code": code, "ok": True, "reason": parts[1], "ts": parts[2]}
    if len(parts) < 5:
        return {"code": code, "ok": False, "reason": None, "max": None, "avg": None, "ts": None}
    return {
        "code": code,
        "ok": True,
        "reason": parts[1],
        "max": parts[2],
        "avg": parts[3],
        "ts": parts[4],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bind-host", default="127.0.0.1")
    ap.add_argument("--bind-port", type=int, default=2000)
    ap.add_argument("--target-host", default="127.0.0.1")
    ap.add_argument("--target-port", type=int, default=2001)
    ap.add_argument("--ready-interval", type=float, default=1.0)
    ap.add_argument("--status-port", type=int, default=0)
    args = ap.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.bind_host, args.bind_port))
    sock.setblocking(False)

    status_sock = None
    if args.status_port:
        status_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        status_sock.bind((args.bind_host, args.status_port))
        status_sock.setblocking(False)

    last_ready = 0.0
    print(f"[robot] UDP bind {args.bind_host}:{args.bind_port}")
    print(f"[robot] READY -> {args.target_host}:{args.target_port} every {args.ready_interval}s")
    if status_sock:
        print(f"[robot] STATUS listen {args.bind_host}:{args.status_port}")

    while True:
        now = time.time()
        if now - last_ready >= args.ready_interval:
            try:
                sock.sendto(b"READY", (args.target_host, args.target_port))
            except (ConnectionResetError, OSError) as e:
                # Windows ICMP port-unreachable (10054) — DTS not listening yet
                print(f"[robot] sendto READY failed (harmless): {e}")
            last_ready = now

        sockets = [sock]
        if status_sock:
            sockets.append(status_sock)
        try:
            readable, _, _ = select.select(sockets, [], [], 0.5)
        except OSError:
            continue
        if not readable:
            continue

        for rsock in readable:
            try:
                data, addr = rsock.recvfrom(65535)
            except (ConnectionResetError, OSError) as e:
                # Windows 10054: previous sendto triggered ICMP unreachable
                print(f"[robot] recvfrom failed (harmless): {e}")
                continue
            payload = data.decode("ascii", errors="ignore").strip()
            if rsock is status_sock:
                parsed = try_parse_status(payload)
                if parsed and parsed.get("ok"):
                    if parsed["code"] == "1004":
                        print(f"[robot] status {addr}: code={parsed['code']} reason={parsed['reason']} ts={parsed['ts']}")
                    else:
                        print(f"[robot] status {addr}: code={parsed['code']} reason={parsed['reason']} max={parsed['max']} avg={parsed['avg']} ts={parsed['ts']}")
                else:
                    print(f"[robot] status {addr}: {payload}")
                continue

            print(f"[robot] recv {addr}: {payload}")

            comma = try_parse_comma(payload)
            if comma:
                warn = ""
                if comma["cnt"] % 3 != 0:
                    warn = " (WARN: cnt not multiple of 3)"
                if not comma["ok"]:
                    warn = " (WARN: field count mismatch)"
                print(f"[robot] comma parse: code={comma['code']} cnt={comma['cnt']} fields={comma['fields']}/{comma['expected_fields']}{warn}")
                continue

            fixed = try_parse_fixed(payload)
            if fixed:
                print(f"[robot] fixed parse: code={fixed['code']} cnt={fixed['cnt']}")
                continue

            print("[robot] parse failed")


if __name__ == "__main__":
    main()
