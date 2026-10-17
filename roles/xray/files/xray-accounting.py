#!/usr/bin/env python3
"""
Xray Traffic Accounting & Quota Enforcement Script
Managed by Ansible (roles/xray)

Responsibilities:
1. Periodically query Xray's built-in StatsService via `xray api statsquery -reset=true`.
2. Persist per-user (by email) and per-inbound/outbound traffic counters across Xray restarts
   in /var/lib/xray/usage.json, aligned to the node's custom `billing_day`.
3. Apply the node's `traffic_multiplier` (e.g. 2x for bidirectional VPS billing).
4. Enforce per-user traffic quotas dynamically via Xray's HandlerService (`xray api rmu` / `adu`)
   without restarting Xray or interrupting other users.
5. Export Prometheus metrics to node_exporter's textfile_collector for VictoriaMetrics.
"""

import calendar
import datetime
import fcntl
import json
import os
import subprocess
import sys
import time
from typing import Any, Dict, Optional, Set

CONFIG_PATH = "/usr/local/etc/xray/accounting.json"
KIB = 1024
MIB = 1024 ** 2
GIB = 1024 ** 3
TIB = 1024 ** 4


def parse_quota_bytes(raw_val: Any) -> int:
    """Parse quota value (int/float in GiB, or string like '20MB', '100GB', '1TB') into bytes."""
    if raw_val is None or raw_val == "":
        return 0
    if isinstance(raw_val, (int, float)):
        return int(float(raw_val) * GIB) if float(raw_val) > 0 else 0
    s = str(raw_val).strip().upper()
    if not s or s == "0":
        return 0
    units = [
        ("TIB", TIB), ("TB", TIB), ("T", TIB),
        ("GIB", GIB), ("GB", GIB), ("G", GIB),
        ("MIB", MIB), ("MB", MIB), ("M", MIB),
        ("KIB", KIB), ("KB", KIB), ("K", KIB),
        ("B", 1),
    ]
    for suffix, mult in units:
        if s.endswith(suffix):
            num_str = s[: -len(suffix)].strip()
            val = float(num_str) if num_str else 0.0
            return int(val * mult) if val > 0 else 0
    val = float(s)
    return int(val * GIB) if val > 0 else 0


def compute_billing_cycle(today: datetime.date, billing_day: int) -> str:
    """Return the start date (YYYY-MM-DD) of the current billing cycle."""
    day = max(1, min(31, int(billing_day)))
    max_day_this_month = calendar.monthrange(today.year, today.month)[1]
    eff_day_this_month = min(day, max_day_this_month)

    if today.day >= eff_day_this_month:
        return datetime.date(today.year, today.month, eff_day_this_month).isoformat()

    if today.month == 1:
        prev_year, prev_month = today.year - 1, 12
    else:
        prev_year, prev_month = today.year, today.month - 1

    max_day_prev_month = calendar.monthrange(prev_year, prev_month)[1]
    eff_day_prev_month = min(day, max_day_prev_month)
    return datetime.date(prev_year, prev_month, eff_day_prev_month).isoformat()


def run_cmd(args: list[str], stdin_data: Optional[str] = None, timeout: int = 5) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        input=stdin_data,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def get_active_inbound_users(xray_bin: str, api_server: str, inbound_tag: str) -> Optional[Set[str]]:
    """Query currently active users in Xray memory via `xray api inbounduser`."""
    res = run_cmd([xray_bin, "api", "inbounduser", f"--server={api_server}", f"-tag={inbound_tag}"])
    if res.returncode != 0:
        return None
    try:
        payload = json.loads(res.stdout or "{}")
        users = payload.get("users") or []
        return {u.get("email") for u in users if isinstance(u, dict) and u.get("email")}
    except Exception:
        return None


def query_user_online_count(xray_bin: str, api_server: str, email: str) -> int:
    """Query active online IP/session count for a user via `xray api statsonline`."""
    res = run_cmd([xray_bin, "api", "statsonline", f"--server={api_server}", f"-email={email}"])
    if res.returncode != 0 or not res.stdout.strip():
        return 0
    try:
        payload = json.loads(res.stdout)
        stat = payload.get("stat") or {}
        return int(stat.get("value", 0))
    except Exception:
        return 0


def remove_user_from_inbound(xray_bin: str, api_server: str, inbound_tag: str, email: str) -> None:
    run_cmd([xray_bin, "api", "rmu", f"--server={api_server}", f"-tag={inbound_tag}", email])


def add_users_to_inbound(xray_bin: str, api_server: str, xray_config_path: str, emails_to_add: Set[str]) -> None:
    if not emails_to_add or not os.path.exists(xray_config_path):
        return
    try:
        with open(xray_config_path, "r", encoding="utf-8") as f:
            raw_cfg = json.load(f)
        inbounds = []
        for ib in raw_cfg.get("inbounds", []):
            settings = ib.get("settings") or {}
            clients = settings.get("clients") or []
            filtered = [c for c in clients if c.get("email") in emails_to_add]
            if filtered:
                ib_copy = dict(ib)
                ib_copy["settings"] = dict(settings)
                ib_copy["settings"]["clients"] = filtered
                inbounds.append(ib_copy)
        if not inbounds:
            return
        adu_payload = json.dumps({"inbounds": inbounds})
        run_cmd([xray_bin, "api", "adu", f"--server={api_server}", "stdin:"], stdin_data=adu_payload)
    except Exception as exc:
        print(f"[xray-accounting] Failed to dynamically add users {emails_to_add}: {exc}", file=sys.stderr)


def load_state(state_file: str) -> Dict[str, Any]:
    if os.path.exists(state_file):
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception as exc:
            print(f"[xray-accounting] Warning: could not parse {state_file}: {exc}", file=sys.stderr)
    return {"billing_cycle": "", "users": {}, "inbounds": {}, "outbounds": {}}


def atomic_write_text(path: str, content: str, mode: int = 0o644) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp_path = f"{path}.tmp.{os.getpid()}"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(content)
    os.chmod(tmp_path, mode)
    os.replace(tmp_path, path)


def write_prom_metrics(
    prom_file: str,
    node: str,
    billing_day: int,
    billing_cycle: str,
    traffic_multiplier: float,
    configured_users: Dict[str, Any],
    state: Dict[str, Any],
    online_counts: Dict[str, int],
) -> None:
    prom_dir = os.path.dirname(prom_file)
    if not prom_dir or not os.path.isdir(prom_dir):
        return

    lines = [
        "# HELP xray_billing_info Current Xray billing configuration info.",
        "# TYPE xray_billing_info gauge",
        f'xray_billing_info{{xray_node="{node}",billing_cycle="{billing_cycle}"}} {billing_day}',
        "# HELP xray_traffic_multiplier Configured VPS billing multiplier (e.g. 2 for bidirectional).",
        "# TYPE xray_traffic_multiplier gauge",
        f'xray_traffic_multiplier{{xray_node="{node}"}} {traffic_multiplier}',
        "# HELP xray_user_cycle_traffic_bytes Raw user traffic bytes in the current billing cycle.",
        "# TYPE xray_user_cycle_traffic_bytes gauge",
        "# HELP xray_user_cycle_billed_bytes Billed user traffic bytes (with multiplier) in the current billing cycle.",
        "# TYPE xray_user_cycle_billed_bytes gauge",
        "# HELP xray_user_total_traffic_bytes Monotonic cumulative raw user traffic bytes.",
        "# TYPE xray_user_total_traffic_bytes counter",
        "# HELP xray_user_total_billed_bytes Monotonic cumulative billed user traffic bytes.",
        "# TYPE xray_user_total_billed_bytes counter",
        "# HELP xray_user_quota_bytes Configured monthly billed traffic quota in bytes (0 = unlimited).",
        "# TYPE xray_user_quota_bytes gauge",
        "# HELP xray_user_throttled Whether the user is currently throttled/removed due to quota (1 = throttled, 0 = active).",
        "# TYPE xray_user_throttled gauge",
        "# HELP xray_user_online_sessions Active online sessions/IPs for the user.",
        "# TYPE xray_user_online_sessions gauge",
    ]

    users_state = state.get("users", {})
    all_emails = sorted(set(configured_users.keys()) | set(users_state.keys()))

    for email in all_emails:
        u_stat = users_state.get(email, {})
        u_cfg = configured_users.get(email, {})
        raw_quota = u_cfg.get("quota", u_cfg.get("quota_gb", 0))
        quota_bytes = parse_quota_bytes(raw_quota)

        c_up = int(u_stat.get("cycle_up", 0))
        c_down = int(u_stat.get("cycle_down", 0))
        c_billed = int(u_stat.get("cycle_billed", int((c_up + c_down) * traffic_multiplier)))

        t_up = int(u_stat.get("total_up", 0))
        t_down = int(u_stat.get("total_down", 0))
        t_billed = int(u_stat.get("total_billed", int((t_up + t_down) * traffic_multiplier)))

        throttled = 1 if u_stat.get("throttled", False) else 0
        online = int(online_counts.get(email, 0))

        lines.append(f'xray_user_cycle_traffic_bytes{{xray_node="{node}",email="{email}",direction="uplink"}} {c_up}')
        lines.append(f'xray_user_cycle_traffic_bytes{{xray_node="{node}",email="{email}",direction="downlink"}} {c_down}')
        lines.append(f'xray_user_cycle_billed_bytes{{xray_node="{node}",email="{email}"}} {c_billed}')
        lines.append(f'xray_user_total_traffic_bytes{{xray_node="{node}",email="{email}",direction="uplink"}} {t_up}')
        lines.append(f'xray_user_total_traffic_bytes{{xray_node="{node}",email="{email}",direction="downlink"}} {t_down}')
        lines.append(f'xray_user_total_billed_bytes{{xray_node="{node}",email="{email}"}} {t_billed}')
        lines.append(f'xray_user_quota_bytes{{xray_node="{node}",email="{email}"}} {quota_bytes}')
        lines.append(f'xray_user_throttled{{xray_node="{node}",email="{email}"}} {throttled}')
        lines.append(f'xray_user_online_sessions{{xray_node="{node}",email="{email}"}} {online}')

    inbounds_state = state.get("inbounds", {})
    if inbounds_state:
        lines.append("# HELP xray_inbound_total_traffic_bytes Monotonic cumulative inbound traffic bytes.")
        lines.append("# TYPE xray_inbound_total_traffic_bytes counter")
        for tag, ib_stat in sorted(inbounds_state.items()):
            lines.append(f'xray_inbound_total_traffic_bytes{{xray_node="{node}",tag="{tag}",direction="uplink"}} {int(ib_stat.get("total_up", 0))}')
            lines.append(f'xray_inbound_total_traffic_bytes{{xray_node="{node}",tag="{tag}",direction="downlink"}} {int(ib_stat.get("total_down", 0))}')

    atomic_write_text(prom_file, "\n".join(lines) + "\n")


def main() -> int:
    if not os.path.exists(CONFIG_PATH):
        return 0

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    node = cfg.get("node", "unknown")
    api_server = cfg.get("api_server", "127.0.0.1:10085")
    inbound_tag = cfg.get("inbound_tag", "vless-in")
    xray_bin = cfg.get("xray_bin", "/usr/local/bin/xray")
    xray_config = cfg.get("xray_config", "/usr/local/etc/xray/config.json")
    state_file = cfg.get("state_file", "/var/lib/xray/usage.json")
    prom_file = cfg.get("prom_file", "/var/lib/node_exporter/textfile_collector/xray_traffic.prom")
    billing_day = int(cfg.get("billing_day", 1))
    traffic_multiplier = float(cfg.get("traffic_multiplier", 2.0))
    configured_users: Dict[str, Any] = cfg.get("users", {})

    os.makedirs(os.path.dirname(state_file), exist_ok=True)
    lock_path = f"{state_file}.lock"
    with open(lock_path, "w", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)

        state = load_state(state_file)
        state.setdefault("users", {})
        state.setdefault("inbounds", {})
        state.setdefault("outbounds", {})

        current_cycle = compute_billing_cycle(datetime.date.today(), billing_day)
        if state.get("billing_cycle") != current_cycle:
            state["billing_cycle"] = current_cycle
            for u_stat in state["users"].values():
                u_stat["cycle_up"] = 0
                u_stat["cycle_down"] = 0
                u_stat["cycle_billed"] = 0
                u_stat["throttled"] = False
            for ib_stat in state["inbounds"].values():
                ib_stat["cycle_up"] = 0
                ib_stat["cycle_down"] = 0
            for ob_stat in state["outbounds"].values():
                ob_stat["cycle_up"] = 0
                ob_stat["cycle_down"] = 0

        # Ensure all configured users exist in state
        for email in configured_users:
            state["users"].setdefault(
                email,
                {
                    "cycle_up": 0,
                    "cycle_down": 0,
                    "cycle_billed": 0,
                    "total_up": 0,
                    "total_down": 0,
                    "total_billed": 0,
                    "throttled": False,
                },
            )

        # 1. Query and reset incremental traffic counters from Xray
        attempts = 6 if "--wait-api" in sys.argv else 1
        stats_res = None
        for attempt in range(attempts):
            stats_res = run_cmd([xray_bin, "api", "statsquery", f"--server={api_server}", "-reset=true"])
            if stats_res.returncode == 0:
                break
            if attempt + 1 < attempts:
                time.sleep(0.5)
        online_counts: Dict[str, int] = {}

        if stats_res.returncode == 0 and stats_res.stdout.strip():
            try:
                stats_payload = json.loads(stats_res.stdout)
                for item in stats_payload.get("stat") or []:
                    name = item.get("name", "")
                    val = int(item.get("value", 0))
                    parts = name.split(">>>")
                    if len(parts) == 4 and parts[0] == "user" and parts[2] == "traffic":
                        email, direction = parts[1], parts[3]
                        u_entry = state["users"].setdefault(
                            email,
                            {
                                "cycle_up": 0,
                                "cycle_down": 0,
                                "cycle_billed": 0,
                                "total_up": 0,
                                "total_down": 0,
                                "total_billed": 0,
                                "throttled": False,
                            },
                        )
                        if direction == "uplink":
                            u_entry["cycle_up"] = int(u_entry.get("cycle_up", 0)) + val
                            u_entry["total_up"] = int(u_entry.get("total_up", 0)) + val
                        elif direction == "downlink":
                            u_entry["cycle_down"] = int(u_entry.get("cycle_down", 0)) + val
                            u_entry["total_down"] = int(u_entry.get("total_down", 0)) + val
                    elif len(parts) == 3 and parts[0] == "user" and parts[2] == "online":
                        online_counts[parts[1]] = val
                    elif len(parts) == 4 and parts[0] in ("inbound", "outbound") and parts[2] == "traffic":
                        bucket = state["inbounds"] if parts[0] == "inbound" else state["outbounds"]
                        tag, direction = parts[1], parts[3]
                        b_entry = bucket.setdefault(
                            tag, {"cycle_up": 0, "cycle_down": 0, "total_up": 0, "total_down": 0}
                        )
                        if direction == "uplink":
                            b_entry["cycle_up"] = int(b_entry.get("cycle_up", 0)) + val
                            b_entry["total_up"] = int(b_entry.get("total_up", 0)) + val
                        elif direction == "downlink":
                            b_entry["cycle_down"] = int(b_entry.get("cycle_down", 0)) + val
                            b_entry["total_down"] = int(b_entry.get("total_down", 0)) + val
            except Exception as exc:
                print(f"[xray-accounting] Warning: failed to parse statsquery output: {exc}", file=sys.stderr)

        # 2. Update billed bytes and enforce quotas
        active_inbound_users = get_active_inbound_users(xray_bin, api_server, inbound_tag)
        emails_to_restore: Set[str] = set()

        for email, u_entry in state["users"].items():
            c_up = int(u_entry.get("cycle_up", 0))
            c_down = int(u_entry.get("cycle_down", 0))
            t_up = int(u_entry.get("total_up", 0))
            t_down = int(u_entry.get("total_down", 0))

            c_billed = int((c_up + c_down) * traffic_multiplier)
            t_billed = int((t_up + t_down) * traffic_multiplier)
            u_entry["cycle_billed"] = c_billed
            u_entry["total_billed"] = t_billed

            if email not in configured_users:
                continue

            if email not in online_counts and stats_res.returncode == 0:
                online_counts[email] = query_user_online_count(xray_bin, api_server, email)

            raw_quota = configured_users[email].get("quota", configured_users[email].get("quota_gb", 0))
            quota_bytes = parse_quota_bytes(raw_quota)
            should_throttle = (quota_bytes > 0) and (c_billed >= quota_bytes)
            was_throttled = bool(u_entry.get("throttled", False))
            u_entry["throttled"] = should_throttle

            if stats_res.returncode == 0:
                if should_throttle:
                    if active_inbound_users is None or email in active_inbound_users:
                        remove_user_from_inbound(xray_bin, api_server, inbound_tag, email)
                else:
                    if (active_inbound_users is not None and email not in active_inbound_users) or (
                        active_inbound_users is None and was_throttled
                    ):
                        emails_to_restore.add(email)

        if emails_to_restore and stats_res.returncode == 0:
            add_users_to_inbound(xray_bin, api_server, xray_config, emails_to_restore)

        state["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        atomic_write_text(state_file, json.dumps(state, indent=2, sort_keys=True) + "\n")
        write_prom_metrics(
            prom_file=prom_file,
            node=node,
            billing_day=billing_day,
            billing_cycle=current_cycle,
            traffic_multiplier=traffic_multiplier,
            configured_users=configured_users,
            state=state,
            online_counts=online_counts,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
