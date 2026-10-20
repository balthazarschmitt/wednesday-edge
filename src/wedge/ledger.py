"""The append-only forecast ledger: file layout, write-once JSON, and the CI integrity check.

Layout under a ledger root (`ledger/`, or `ledger/shadow/` before launch):
  forecasts/{period}-crude.json             forecast or missed record, written once
  overrides/{period}-crude.json             human override, committed before the deadline
  consensus/{period}-api.json               API (American Petroleum Institute) print
  consensus/{period}-consensus-{slug}.json  analyst consensus, one file per source
  scores/{period}-crude.json                score, written once the actual is published
"""

import json
import re
import subprocess
from datetime import date, datetime
from pathlib import Path

from wedge import config, releases

SCHEMA_VERSION = 1
COMMODITY = "crude"
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"  # git's empty tree, for first pushes
FORECAST_STATUSES = {"forecast", "missed"}


class LedgerError(RuntimeError):
    pass


def root(shadow: bool) -> Path:
    return config.LEDGER_DIR / "shadow" if shadow else config.LEDGER_DIR


def forecast_path(base: Path, period: date) -> Path:
    return base / "forecasts" / f"{period}-{COMMODITY}.json"


def score_path(base: Path, period: date) -> Path:
    return base / "scores" / f"{period}-{COMMODITY}.json"


def override_path(base: Path, period: date) -> Path:
    return base / "overrides" / f"{period}-{COMMODITY}.json"


def api_path(base: Path, period: date) -> Path:
    return base / "consensus" / f"{period}-api.json"


def consensus_path(base: Path, period: date, source: str) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "-", source.lower()).strip("-")
    if not slug:
        raise LedgerError("consensus source needs a name")
    return base / "consensus" / f"{period}-consensus-{slug}.json"


def period_of(path: Path) -> date:
    return date.fromisoformat(path.name[:10])


def iso(dt: datetime) -> str:
    return dt.astimezone(releases.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def write_once(path: Path, payload: dict) -> None:
    """Create `path` with `payload`; refuse to overwrite (the ledger is append-only)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps({"schema_version": SCHEMA_VERSION, **payload}, indent=2, sort_keys=False)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as fh:
            fh.write(text + "\n")
    except FileExistsError:
        raise LedgerError(f"{path.name} already exists; the ledger is append-only") from None


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def check_entry(rel_path: str, entry: dict) -> list[str]:
    """Content rules for a newly added ledger file."""
    problems = []
    if entry.get("schema_version") != SCHEMA_VERSION:
        problems.append(f"{rel_path}: unknown schema_version")
    if "/forecasts/" in f"/{rel_path}":
        status = entry.get("status")
        if status not in FORECAST_STATUSES:
            problems.append(f"{rel_path}: status must be one of {sorted(FORECAST_STATUSES)}")
        if status == "forecast":
            period = date.fromisoformat(entry["target_period"])
            if parse_iso(entry["created_at"]) >= releases.deadline(period):
                problems.append(f"{rel_path}: forecast created after its deadline")
    if "/overrides/" in f"/{rel_path}":
        period = date.fromisoformat(entry["target_period"])
        if parse_iso(entry["logged_at"]) >= releases.deadline(period):
            problems.append(f"{rel_path}: override logged after its deadline")
    return problems


def integrity_violations(base: str | None, head: str = "HEAD", repo: Path = config.REPO_ROOT):
    """Every change under ledger/ between `base` and `head` must be a new file with valid content.

    README files are documentation and may change.
    """
    if not base or set(base) == {"0"}:
        base = EMPTY_TREE
    diff = subprocess.run(
        ["git", "diff", "--name-status", "--no-renames", base, head, "--", "ledger/"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    problems = []
    for line in diff.splitlines():
        status, rel_path = line.split("\t", 1)
        if Path(rel_path).name == "README.md":
            continue
        if status != "A":
            problems.append(f"{rel_path}: {status} (only additions are allowed)")
            continue
        if rel_path.endswith(".json"):
            content = subprocess.run(
                ["git", "show", f"{head}:{rel_path}"],
                cwd=repo,
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            try:
                problems += check_entry(rel_path, json.loads(content))
            except (ValueError, KeyError) as exc:
                problems.append(f"{rel_path}: unreadable ({exc})")
    return problems
