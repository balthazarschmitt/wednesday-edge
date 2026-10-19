"""Central configuration: paths, EIA series IDs, and settings read from the environment."""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
DB_PATH = DATA_DIR / "wedge.duckdb"
LEDGER_DIR = REPO_ROOT / "ledger"

EIA_API_BASE = "https://api.eia.gov/v2"

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

PRIMARY_TARGET = "crude_commercial"


def eia_api_key() -> str:
    """Return the EIA API key from the environment; never hard-code it."""
    key = os.environ.get("EIA_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "EIA_API_KEY is not set. Register free at https://www.eia.gov/opendata/register.php "
            "and set it locally (see .env.example) or as a GitHub Actions secret."
        )
    return key
