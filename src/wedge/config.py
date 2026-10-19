"""Central configuration: paths, EIA series IDs, and settings read from the environment."""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
DB_PATH = DATA_DIR / "wedge.duckdb"
LEDGER_DIR = REPO_ROOT / "ledger"

EIA_API_BASE = "https://api.eia.gov/v2"
# Fallback when the API is down: one legacy XLS workbook per series.
EIA_XLS_URL = "https://www.eia.gov/dnav/pet/hist_xls/{series_id}w.xls"
# EIA latency reached 44s in the Phase 1 spike; one call timed out at 60s.
HTTP_TIMEOUT_S = 120.0

# All series live on one route; confirmed in the Phase 1 data spike (pm/adr/0002-data-spike.md).
EIA_WEEKLY_ROUTE = "petroleum/sum/sndw"

# Weekly stock levels (thousand barrels).
STOCK_SERIES = {
    "crude_commercial": "WCESTUS1",
    "crude_spr": "WCSSTUS1",
    "cushing": "W_EPC0_SAX_YCUOK_MBBL",
    "gasoline": "WGTSTUS1",
    "distillate": "WDISTUS1",
    "jet": "WKJSTUS1",
    "propane": "WPRSTUS1",
}

# Crude balance flows (thousand barrels per day) and refinery utilization (%).
# EIA publishes no crude adjustment series; it is derived as the balance residual.
FLOW_SERIES = {
    "production": "WCRFPUS2",
    "imports_commercial": "WCEIMUS2",
    "exports": "WCREXUS2",
    "refinery_input": "WCRRIUS2",
    "refinery_utilization": "WPULEUS3",
}

ALL_SERIES = {**STOCK_SERIES, **FLOW_SERIES}
SERIES_NAMES = {sid: name for name, sid in ALL_SERIES.items()}

PRIMARY_TARGET = "crude_commercial"


def load_dotenv(path: Path = REPO_ROOT / ".env") -> None:
    """Load KEY=VALUE lines from a local .env without overriding real environment variables."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip())


def eia_api_key() -> str:
    """Return the EIA API key from the environment; never hard-code it."""
    key = os.environ.get("EIA_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "EIA_API_KEY is not set. Register free at https://www.eia.gov/opendata/register.php "
            "and set it locally (see .env.example) or as a GitHub Actions secret."
        )
    return key
