"""Run the Vercel build locally and import every function from its bundle.

Catches dependency and packaging problems before a deploy, without touching the
checkout: the working tree (tracked and untracked files, minus anything
gitignored, so no ``.env.local`` or ``endpoints.json``) is copied to a temporary
directory, ``vercel build`` runs there, and each entry point is imported from the
bundle with only the bundled packages on the path. Nothing is deployed, no
environment variables are pulled, and no RPC or Grafana calls are made.

Usage:
    uv run scripts/vercel_build_check.py [--config vercel.fra1.json] [--keep]
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
BUNDLE_LIMIT_MB = 500

IMPORT_PROBE = """
import importlib, sys
mods = sys.argv[1:]
for m in mods:
    importlib.import_module(m)
import vc__handler__python
version = sys.version.split()[0]
print(f"{len(mods)} entry points and the Vercel handler import on {version}")
"""


def run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> str:
    """Run a command, exit with its output if it fails, return stdout."""
    result = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"FAILED: {' '.join(cmd)}\n{result.stdout}\n{result.stderr}")
    return result.stdout


def copy_working_tree(dest: Path) -> None:
    """Copy tracked and untracked, non-ignored files into ``dest``."""
    listed = run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], REPO
    )
    for rel in filter(None, listed.split("\0")):
        src = REPO / rel
        if src.is_file():
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest / rel)


def link_project(dest: Path) -> None:
    """Reuse the local project link (IDs only) so ``vercel build`` needs no pull."""
    link = REPO / ".vercel" / "project.json"
    if not link.exists():
        sys.exit("No .vercel/project.json: run `vercel link` in this repo first.")
    project = json.loads(link.read_text())
    project["settings"] = {"framework": None}
    (dest / ".vercel").mkdir()
    (dest / ".vercel" / "project.json").write_text(json.dumps(project))


def materialise(build_root: Path, func_dir: Path, out: Path) -> str:
    """Lay out a function bundle as Vercel would load it; return its runtime."""
    config: dict[str, Any] = json.loads((func_dir / ".vc-config.json").read_text())
    file_map: dict[str, str] = config["filePathMap"]
    for dst, src in file_map.items():
        target = out / dst
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(Path(src) if Path(src).is_absolute() else build_root / src, target)
    for handler in func_dir.glob("*.py"):
        shutil.copy2(handler, out / handler.name)
    runtime: str = config["runtime"]
    return runtime


def bundle_size_mb(path: Path) -> float:
    """Return the total size of files under ``path`` in MB."""
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1e6


def entry_modules(bundle: Path) -> list[str]:
    """Return dotted module names for every Python file under ``api/``."""
    return sorted(
        ".".join(p.relative_to(bundle).with_suffix("").parts)
        for p in (bundle / "api").rglob("*.py")
    )


def main() -> None:
    """Build in a temp copy, then import-check the bundle."""
    parser = argparse.ArgumentParser(description="Local Vercel build check.")
    parser.add_argument("--config", help="region config, e.g. vercel.fra1.json")
    parser.add_argument("--keep", action="store_true", help="keep the temp dir")
    args = parser.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="vercel-build-check-"))
    try:
        copy_working_tree(tmp)
        link_project(tmp)
        build_cmd = ["vercel", "build", "--non-interactive"]
        if args.config:
            build_cmd += ["--local-config", args.config]
        print(f"Building in {tmp} ...")
        run(build_cmd, tmp)

        funcs = sorted((tmp / ".vercel/output/functions").rglob("*.func"))
        if not funcs:
            sys.exit("Build produced no functions.")
        print(f"Built {len(funcs)} functions.")

        bundle = tmp / "bundle"
        runtime = materialise(tmp, funcs[0], bundle)
        size = bundle_size_mb(bundle)
        print(f"Bundle: {size:.0f} MB of {BUNDLE_LIMIT_MB} MB, {runtime}")
        if size > BUNDLE_LIMIT_MB:
            sys.exit("Bundle exceeds the Vercel size limit.")

        python = runtime.removeprefix("python")
        env = {
            "PATH": os.environ["PATH"],
            "HOME": os.environ["HOME"],
            "PYTHONPATH": "_vendor:.",
            "SOLANA_PRIVATE_KEY": "",
        }
        probe = ["uv", "run", "--no-project", "--python", python, "python", "-c"]
        print(run([*probe, IMPORT_PROBE, *entry_modules(bundle)], bundle, env).strip())
        print("OK")
    finally:
        if args.keep:
            print(f"Kept {tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
