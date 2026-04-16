# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "requests",
#   "python-dotenv",
# ]
# ///
"""CLI tool to pull, push, and diff Grafana dashboards via the Grafana HTTP API."""

import hashlib
import json
import os
import re
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

REQUIRED_VARS = ["GRAFANA_URL", "GRAFANA_TOKEN", "GRAFANA_FOLDER"]
STATE_FILE = ".grafana_state.json"


def load_config() -> dict:
    """Load and validate required Grafana config from environment variables."""
    missing = [v for v in REQUIRED_VARS if not os.getenv(v)]
    if missing:
        for v in missing:
            print(f"[ERROR] Missing required env var: {v}")
        sys.exit(1)
    return {
        "url": os.environ["GRAFANA_URL"].rstrip("/"),
        "token": os.environ["GRAFANA_TOKEN"],
        "folder": os.environ["GRAFANA_FOLDER"],
    }


def load_state() -> dict:
    """Load local state from the state file, returning empty dict if absent."""
    p = Path(STATE_FILE)
    if not p.exists():
        return {}
    return json.loads(p.read_text())


def save_state(state: dict) -> None:
    """Persist state dict to the state file as formatted JSON."""
    Path(STATE_FILE).write_text(json.dumps(state, indent=2))


def compute_checksum(data: dict) -> str:
    """Return a deterministic SHA-256 hex digest of the JSON-serialised data."""
    serialized = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode()).hexdigest()


def _headers(cfg: dict) -> dict:
    return {
        "Authorization": f"Bearer {cfg['token']}",
        "Content-Type": "application/json",
    }


def api_get(cfg: dict, path: str) -> dict | list:
    """Perform a GET request against the Grafana API, raising on non-200."""
    resp = requests.get(f"{cfg['url']}{path}", headers=_headers(cfg))
    if resp.status_code != 200:
        print(f"[ERROR] GET {path} → {resp.status_code}: {resp.text}")
        raise RuntimeError(f"API error {resp.status_code}")
    return resp.json()


def api_post(cfg: dict, path: str, payload: dict) -> dict:
    """Perform a POST request against the Grafana API, raising on non-200/201."""
    resp = requests.post(f"{cfg['url']}{path}", headers=_headers(cfg), json=payload)
    if resp.status_code not in (200, 201):
        print(f"[ERROR] POST {path} → {resp.status_code}: {resp.text}")
        raise RuntimeError(f"API error {resp.status_code}")
    return resp.json()


def resolve_folder_uid(cfg: dict) -> str:
    """Return the Grafana folder UID for the configured folder name, or exit."""
    results = api_get(cfg, "/api/search?type=dash-db&limit=200")
    for d in results:
        if d.get("folderTitle") == cfg["folder"]:
            return d["folderUid"]
    print(f"[ERROR] Folder '{cfg['folder']}' not found in Grafana")
    sys.exit(1)


def make_slug(title: str, uid: str, existing: set) -> str:
    """Generate a URL-safe slug from title, appending uid if already taken."""
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    if slug in existing:
        slug = f"{slug}-{uid}"
    return slug


def cmd_pull(cfg: dict) -> None:
    """Pull all dashboards from Grafana and write them to the local dashboards/ dir."""
    folder_uid = resolve_folder_uid(cfg)
    results = api_get(cfg, f"/api/search?type=dash-db&folderUIDs={folder_uid}")
    Path("dashboards").mkdir(exist_ok=True)
    state = load_state()
    used_slugs = {v["slug"] for v in state.values()}

    for item in results:
        uid = item["uid"]
        detail = api_get(cfg, f"/api/dashboards/uid/{uid}")
        dashboard = detail["dashboard"]
        meta = detail["meta"]
        title = dashboard.get("title", uid)
        if uid in state:
            slug = state[uid]["slug"]
        else:
            slug = make_slug(title, uid, used_slugs)
            used_slugs.add(slug)

        filepath = Path("dashboards") / f"{slug}.json"
        content = json.dumps(dashboard, indent=2)
        filepath.write_text(content)

        state[uid] = {
            "title": title,
            "slug": slug,
            "folder_uid": meta.get("folderUid", folder_uid),
            "checksum": compute_checksum(dashboard),
            "remote_updated": meta.get("updated", ""),
        }
        print(f"[pull]  {slug} → dashboards/{slug}.json")

    save_state(state)


def compute_diff(state: dict, remote_meta: dict) -> tuple[list, list]:
    """Return (changed, conflicts) lists by comparing local files to state/remote."""
    slug_to_uid = {v["slug"]: k for k, v in state.items()}
    changed = []
    conflicts = []

    dashboard_dir = Path("dashboards")
    if not dashboard_dir.exists():
        return [], []

    for filepath in sorted(dashboard_dir.glob("*.json")):
        slug = filepath.stem
        if slug not in slug_to_uid:
            print(f"[WARN]  {slug} → not in state, run pull first — skipping")
            continue

        uid = slug_to_uid[slug]
        entry = state[uid]
        current_data = json.loads(filepath.read_text())
        current_checksum = compute_checksum(current_data)

        if current_checksum == entry["checksum"]:
            continue

        remote_updated = remote_meta.get(uid, {}).get(
            "updated", entry["remote_updated"]
        )
        if remote_updated != entry["remote_updated"]:
            conflicts.append({"uid": uid, "slug": slug, "entry": entry})
        else:
            changed.append(
                {"uid": uid, "slug": slug, "entry": entry, "data": current_data}
            )

    return changed, conflicts


def cmd_push(cfg: dict, message: str = "") -> None:
    """Push locally changed dashboards to Grafana, skipping conflicts."""
    if not Path(STATE_FILE).exists():
        print("[ERROR] No state file found. Run `pull` first.")
        sys.exit(1)

    state = load_state()

    remote_meta = {}
    for uid in state:
        try:
            detail = api_get(cfg, f"/api/dashboards/uid/{uid}")
            remote_meta[uid] = {"updated": detail["meta"].get("updated", "")}
        except RuntimeError:
            pass

    changed, conflicts = compute_diff(state, remote_meta)

    for item in conflicts:
        print(
            f"[WARN]  {item['slug']} → conflict: remote changed since last pull,"
            " skipping"
        )

    for item in changed:
        uid = item["uid"]
        entry = item["entry"]
        payload = {
            "dashboard": item["data"],
            "folderUid": entry["folder_uid"],
            "overwrite": True,
            "message": message,
        }
        try:
            api_post(cfg, "/api/dashboards/db", payload)
            # Re-fetch to get the new remote timestamp after push
            detail = api_get(cfg, f"/api/dashboards/uid/{uid}")
            state[uid]["checksum"] = compute_checksum(item["data"])
            state[uid]["remote_updated"] = detail["meta"]["updated"]
            print(f"[push]  {item['slug']} → uploaded OK")
        except RuntimeError:
            pass

    save_state(state)


def cmd_status(cfg: dict) -> None:
    """Print a diff of local vs remote dashboards without making any changes."""
    if not Path(STATE_FILE).exists():
        print("[ERROR] No state file found. Run `pull` first.")
        sys.exit(1)

    state = load_state()

    remote_meta = {}
    for uid in state:
        try:
            detail = api_get(cfg, f"/api/dashboards/uid/{uid}")
            remote_meta[uid] = {"updated": detail["meta"].get("updated", "")}
        except RuntimeError:
            pass

    changed, conflicts = compute_diff(state, remote_meta)

    if not changed and not conflicts:
        print("[status] Everything up to date.")
        return

    for item in changed:
        print(f"[changed]  {item['slug']} → would be pushed")
    for item in conflicts:
        print(f"[conflict] {item['slug']} → remote changed since last pull")


def main() -> None:
    """Parse CLI args and dispatch to pull, push, or status command."""
    if len(sys.argv) < 2 or sys.argv[1] not in ("pull", "push", "status"):
        print("Usage: uv run grafana_sync.py <pull|push|status> [-m 'message']")
        sys.exit(1)

    cfg = load_config()
    command = sys.argv[1]
    args = sys.argv[2:]

    message = ""
    if "-m" in args:
        idx = args.index("-m")
        if idx + 1 < len(args):
            message = args[idx + 1]

    if command == "pull":
        cmd_pull(cfg)
    elif command == "push":
        cmd_push(cfg, message=message)
    elif command == "status":
        cmd_status(cfg)


if __name__ == "__main__":
    main()
