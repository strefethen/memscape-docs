"""Stage only tracked public HTML and assets for a static Cloudflare deploy."""
from pathlib import Path
import shutil
import subprocess
from demo_snapshot import validate_snapshot

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "_site"
PAGES = {"index.html", "journey.html", "privacy-policy.html", "support.html"}
CONTROLS = {"_headers"}


def stage():
    tracked = subprocess.check_output(
        ["git", "ls-files", "-z"], cwd=ROOT
    ).decode().split("\0")
    allowed = {name for name in tracked if name in PAGES | CONTROLS or name.startswith("assets/")}
    allowed |= validate_snapshot(ROOT, set(tracked))
    if not PAGES | CONTROLS <= allowed:
        raise SystemExit("The four public HTML pages and deployment controls must be tracked before staging")
    for name in sorted(allowed):
        source = ROOT / name
        destination = DESTINATION / name
        if not source.is_file() or any(p.is_symlink() for p in (source, *source.parents)):
            raise SystemExit(f"Public source must be a regular file: {name}")
        if any(p.is_symlink() for p in (destination, *destination.parents)):
            raise SystemExit(f"Staging path must not be a symlink: {name}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    staged = {str(path.relative_to(DESTINATION)) for path in DESTINATION.rglob("*") if path.is_file()}
    if staged != allowed:
        raise SystemExit(f"Unexpected staged files; remove them before deploying: {sorted(staged - allowed)}")
    for name in allowed:
        if (ROOT / name).read_bytes() != (DESTINATION / name).read_bytes():
            raise SystemExit(f"Staged bytes differ: {name}")
    print(f"Staged {len(allowed - CONTROLS)} public HTML/assets and {len(CONTROLS)} deployment control with exact source bytes")


if __name__ == "__main__":
    stage()
