# grafana-sync

A CLI tool to sync Grafana dashboards to/from local JSON files, enabling version control for your dashboards.

## Requirements

- [uv](https://github.com/astral-sh/uv)

## Setup

Create a `.env` file:

```env
GRAFANA_URL=https://your-grafana-instance.com
GRAFANA_TOKEN=your-service-account-token
GRAFANA_FOLDER=Your Folder Name
```

## Usage

```bash
# Download all dashboards from the configured folder
uv run grafana_sync.py pull

# Upload local changes to Grafana
uv run grafana_sync.py push

# Upload with a version note
uv run grafana_sync.py push -m "Add memory usage panel"

# Show local vs remote diff
uv run grafana_sync.py status
```

## How it works

- `pull` — fetches all dashboards from the Grafana folder and saves them as JSON files under `dashboards/`
- `push` — uploads changed local files to Grafana, with conflict detection
- `status` — compares local checksums against remote to show what has changed

State is tracked in `.grafana_state.json` (add to `.gitignore` if preferred, or commit it to track last-synced versions).
