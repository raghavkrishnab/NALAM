"""Loads the bilingual scheme catalogue from disk."""

import json
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# schemes_master.json is generated from the official TN CSV by tools/ingest_csv.py
# and covers state schemes. schemes_central.json is hand-curated and covers the
# Government of India schemes the state CSV omits (PM-KISAN, MGNREGA, PM-JAY and
# the rest), which are the ones citizens ask about most often.
SOURCES = ["schemes_master.json", "schemes_central.json"]

# Central NSAP pensions whose Tamil Nadu implementations already appear in the
# state file - listing both would show the same benefit twice.
SUPERSEDED_IDS = {"in-ignwps", "in-nsp-disability"}


@lru_cache(maxsize=1)
def load_schemes() -> list[dict]:
    """Read and merge every scheme file. Cached; call load_schemes.cache_clear() to reload."""
    schemes: list[dict] = []
    seen: set[str] = set()

    for filename in SOURCES:
        path = DATA_DIR / filename
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as handle:
            for scheme in json.load(handle):
                if scheme["id"] in SUPERSEDED_IDS:
                    continue
                if scheme["id"] in seen:
                    raise ValueError(f"Duplicate scheme id in {filename}: {scheme['id']}")
                seen.add(scheme["id"])
                schemes.append(scheme)

    if not schemes:
        raise RuntimeError(f"No scheme data found in {DATA_DIR}")

    schemes.sort(key=lambda s: -s.get("priority", 0))
    return schemes


def localise(value, language: str) -> str:
    """Pull the requested language out of a {'en': ..., 'ta': ...} block."""
    if isinstance(value, dict):
        return value.get(language) or value.get("en") or ""
    return str(value or "")


def all_categories() -> list[str]:
    categories: set[str] = set()
    for scheme in load_schemes():
        categories.update(scheme.get("categories", []))
    return sorted(categories)
