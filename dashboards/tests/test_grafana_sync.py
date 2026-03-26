# Tests for grafana_sync.py
import sys
import pytest
from unittest.mock import MagicMock, patch

# Helper to import without running main()
def import_module():
    if "grafana_sync" in sys.modules:
        return sys.modules["grafana_sync"]
    import grafana_sync
    return grafana_sync

def test_load_config_returns_all_vars(monkeypatch):
    monkeypatch.setenv("GRAFANA_URL", "https://test.grafana.net")
    monkeypatch.setenv("GRAFANA_TOKEN", "token123")
    monkeypatch.setenv("GRAFANA_FOLDER", "MyFolder")
    m = import_module()
    cfg = m.load_config()
    assert cfg["url"] == "https://test.grafana.net"
    assert cfg["token"] == "token123"
    assert cfg["folder"] == "MyFolder"

def test_load_config_exits_on_missing_var(monkeypatch):
    monkeypatch.delenv("GRAFANA_URL", raising=False)
    monkeypatch.delenv("GRAFANA_TOKEN", raising=False)
    monkeypatch.delenv("GRAFANA_FOLDER", raising=False)
    m = import_module()
    with pytest.raises(SystemExit):
        m.load_config()

def test_api_get_returns_json(monkeypatch):
    monkeypatch.setenv("GRAFANA_URL", "https://test.grafana.net")
    monkeypatch.setenv("GRAFANA_TOKEN", "tok")
    monkeypatch.setenv("GRAFANA_FOLDER", "F")
    m = import_module()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"key": "value"}
    with patch("requests.get", return_value=mock_resp):
        result = m.api_get(m.load_config(), "/api/folders")
    assert result == {"key": "value"}

def test_api_get_prints_error_on_non_200(monkeypatch, capsys):
    monkeypatch.setenv("GRAFANA_URL", "https://test.grafana.net")
    monkeypatch.setenv("GRAFANA_TOKEN", "tok")
    monkeypatch.setenv("GRAFANA_FOLDER", "F")
    m = import_module()
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized"
    with patch("requests.get", return_value=mock_resp):
        with pytest.raises(RuntimeError):
            m.api_get(m.load_config(), "/api/folders")
    captured = capsys.readouterr()
    assert "401" in captured.out

def test_resolve_folder_uid_finds_match(monkeypatch):
    monkeypatch.setenv("GRAFANA_URL", "https://test.grafana.net")
    monkeypatch.setenv("GRAFANA_TOKEN", "tok")
    monkeypatch.setenv("GRAFANA_FOLDER", "MyFolder")
    m = import_module()
    search_results = [{"uid": "d1", "folderTitle": "Other", "folderUid": "abc"}, {"uid": "d2", "folderTitle": "MyFolder", "folderUid": "xyz"}]
    with patch.object(m, "api_get", return_value=search_results):
        uid = m.resolve_folder_uid(m.load_config())
    assert uid == "xyz"

def test_resolve_folder_uid_exits_if_not_found(monkeypatch):
    monkeypatch.setenv("GRAFANA_URL", "https://test.grafana.net")
    monkeypatch.setenv("GRAFANA_TOKEN", "tok")
    monkeypatch.setenv("GRAFANA_FOLDER", "Missing")
    m = import_module()
    with patch.object(m, "api_get", return_value=[{"uid": "d1", "folderTitle": "Other", "folderUid": "abc"}]):
        with pytest.raises(SystemExit):
            m.resolve_folder_uid(m.load_config())

import json

STATE_FILE = ".grafana_state.json"

def test_load_state_returns_empty_if_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    m = import_module()
    assert m.load_state() == {}

def test_load_state_reads_existing_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data = {"uid1": {"title": "X", "checksum": "abc"}}
    (tmp_path / STATE_FILE).write_text(json.dumps(data))
    m = import_module()
    assert m.load_state() == data

def test_save_state_writes_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    m = import_module()
    data = {"uid1": {"title": "X"}}
    m.save_state(data)
    written = json.loads((tmp_path / STATE_FILE).read_text())
    assert written == data

def test_compute_checksum_is_deterministic():
    m = import_module()
    data = {"key": "value", "nested": {"a": 1}}
    assert m.compute_checksum(data) == m.compute_checksum(data)
    assert m.compute_checksum(data) != m.compute_checksum({"key": "other"})

def test_make_slug_basic():
    m = import_module()
    assert m.make_slug("My Dashboard", "abc123", set()) == "my-dashboard"

def test_make_slug_strips_special_chars():
    m = import_module()
    assert m.make_slug("CPU Usage (%)!", "abc123", set()) == "cpu-usage"

def test_make_slug_deduplicates_with_uid():
    m = import_module()
    existing = {"my-dashboard"}
    assert m.make_slug("My Dashboard", "abc123", existing) == "my-dashboard-abc123"

def test_cmd_pull_writes_files_and_state(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAFANA_URL", "https://test.grafana.net")
    monkeypatch.setenv("GRAFANA_TOKEN", "tok")
    monkeypatch.setenv("GRAFANA_FOLDER", "MyFolder")
    m = import_module()

    dashboard_json = {"uid": "abc", "title": "My Board", "panels": []}
    search_results = [{"uid": "abc", "title": "My Board"}]
    detail = {"dashboard": dashboard_json, "meta": {"updated": "2026-01-01T00:00:00Z", "folderUid": "xyz"}}

    def fake_api_get(cfg, path):
        if "/api/search" in path and "type=dash-db&limit=200" in path:
            return [{"uid": "abc", "title": "My Board", "folderTitle": "MyFolder", "folderUid": "xyz"}]
        if "/api/search" in path:
            return search_results
        if "/api/dashboards/uid/" in path:
            return detail
        return []

    with patch.object(m, "api_get", side_effect=fake_api_get):
        m.cmd_pull(m.load_config())

    captured = capsys.readouterr()
    assert "[pull]" in captured.out
    assert "my-board.json" in captured.out
    assert (tmp_path / "dashboards" / "my-board.json").exists()
    state = m.load_state()
    assert "abc" in state
    assert state["abc"]["title"] == "My Board"
    assert state["abc"]["folder_uid"] == "xyz"


def test_compute_diff_unchanged(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    m = import_module()
    dashboard = {"uid": "abc", "title": "X"}
    checksum = m.compute_checksum(dashboard)
    (tmp_path / "dashboards").mkdir()
    (tmp_path / "dashboards" / "x.json").write_text(json.dumps(dashboard))
    state = {"abc": {"slug": "x", "checksum": checksum, "remote_updated": "2026-01-01T00:00:00Z", "folder_uid": "f1"}}
    changed, conflicts = m.compute_diff(state, {})
    assert changed == []
    assert conflicts == []

def test_compute_diff_detects_local_change_no_conflict(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    m = import_module()
    original = {"uid": "abc", "title": "X"}
    modified = {"uid": "abc", "title": "X modified"}
    (tmp_path / "dashboards").mkdir()
    (tmp_path / "dashboards" / "x.json").write_text(json.dumps(modified))
    state = {"abc": {"slug": "x", "checksum": m.compute_checksum(original), "remote_updated": "2026-01-01T00:00:00Z", "folder_uid": "f1"}}
    remote_meta = {"abc": {"updated": "2026-01-01T00:00:00Z"}}
    changed, conflicts = m.compute_diff(state, remote_meta)
    assert len(changed) == 1
    assert changed[0]["uid"] == "abc"
    assert conflicts == []

def test_compute_diff_detects_conflict(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    m = import_module()
    original = {"uid": "abc", "title": "X"}
    modified = {"uid": "abc", "title": "X modified"}
    (tmp_path / "dashboards").mkdir()
    (tmp_path / "dashboards" / "x.json").write_text(json.dumps(modified))
    state = {"abc": {"slug": "x", "checksum": m.compute_checksum(original), "remote_updated": "2026-01-01T00:00:00Z", "folder_uid": "f1"}}
    remote_meta = {"abc": {"updated": "2026-03-01T00:00:00Z"}}
    changed, conflicts = m.compute_diff(state, remote_meta)
    assert changed == []
    assert len(conflicts) == 1

def test_compute_diff_warns_file_not_in_state(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    m = import_module()
    (tmp_path / "dashboards").mkdir()
    (tmp_path / "dashboards" / "unknown.json").write_text("{}")
    changed, conflicts = m.compute_diff({}, {})
    captured = capsys.readouterr()
    assert "[WARN]" in captured.out
    assert "unknown" in captured.out

def test_cmd_push_uploads_changed_skips_conflicts(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAFANA_URL", "https://test.grafana.net")
    monkeypatch.setenv("GRAFANA_TOKEN", "tok")
    monkeypatch.setenv("GRAFANA_FOLDER", "MyFolder")
    m = import_module()

    original = {"uid": "abc", "title": "X"}
    modified = {"uid": "abc", "title": "X modified"}
    conflict_original = {"uid": "def", "title": "Y"}
    conflict_modified = {"uid": "def", "title": "Y modified"}

    (tmp_path / "dashboards").mkdir()
    (tmp_path / "dashboards" / "x.json").write_text(json.dumps(modified))
    (tmp_path / "dashboards" / "y.json").write_text(json.dumps(conflict_modified))

    state = {
        "abc": {"slug": "x", "checksum": m.compute_checksum(original), "remote_updated": "2026-01-01T00:00:00Z", "folder_uid": "f1"},
        "def": {"slug": "y", "checksum": m.compute_checksum(conflict_original), "remote_updated": "2026-01-01T00:00:00Z", "folder_uid": "f1"},
    }
    m.save_state(state)

    abc_call_count = {"n": 0}
    def fake_api_get(cfg, path):
        if "abc" in path:
            abc_call_count["n"] += 1
            # Second call is the re-fetch after push — return new timestamp
            ts = "2026-01-01T12:00:00Z" if abc_call_count["n"] > 1 else "2026-01-01T00:00:00Z"
            return {"dashboard": original, "meta": {"updated": ts}}
        if "def" in path:
            return {"dashboard": conflict_original, "meta": {"updated": "2026-03-01T00:00:00Z"}}
        return []

    posted = []
    def fake_api_post(cfg, path, payload):
        posted.append(payload)
        return {"status": "success"}

    with patch.object(m, "api_get", side_effect=fake_api_get), \
         patch.object(m, "api_post", side_effect=fake_api_post):
        m.cmd_push(m.load_config())

    captured = capsys.readouterr()
    assert "[push]" in captured.out
    assert "[WARN]" in captured.out
    assert len(posted) == 1
    # Verify state was updated with the new remote timestamp
    updated_state = m.load_state()
    assert updated_state["abc"]["remote_updated"] == "2026-01-01T12:00:00Z"

def test_cmd_push_exits_if_no_state_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAFANA_URL", "https://test.grafana.net")
    monkeypatch.setenv("GRAFANA_TOKEN", "tok")
    monkeypatch.setenv("GRAFANA_FOLDER", "F")
    m = import_module()
    with pytest.raises(SystemExit):
        m.cmd_push(m.load_config())

def test_cmd_status_prints_diff_without_modifying(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAFANA_URL", "https://test.grafana.net")
    monkeypatch.setenv("GRAFANA_TOKEN", "tok")
    monkeypatch.setenv("GRAFANA_FOLDER", "F")
    m = import_module()

    original = {"uid": "abc", "title": "X"}
    modified = {"uid": "abc", "title": "X modified"}
    (tmp_path / "dashboards").mkdir()
    (tmp_path / "dashboards" / "x.json").write_text(json.dumps(modified))

    state = {"abc": {"slug": "x", "checksum": m.compute_checksum(original), "remote_updated": "2026-01-01T00:00:00Z", "folder_uid": "f1"}}
    m.save_state(state)

    def fake_api_get(cfg, path):
        return {"dashboard": original, "meta": {"updated": "2026-01-01T00:00:00Z"}}

    with patch.object(m, "api_get", side_effect=fake_api_get):
        m.cmd_status(m.load_config())

    captured = capsys.readouterr()
    assert "[changed]" in captured.out
    assert "x" in captured.out
    assert m.load_state() == state
