"""Cached Socrata fetches. Raw responses land in data/raw/ so reruns are offline-friendly."""
import hashlib
import json
import os
import time
from pathlib import Path
from urllib.parse import urlencode

import requests

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"
TOKEN = os.environ.get("SOCRATA_APP_TOKEN")


def query(dataset_id, domain="data.cityofnewyork.us", **params):
    """Run a SoQL query ($-prefixed keys passed without the $), caching the JSON result."""
    q = {f"${k}": v for k, v in params.items()}
    key = hashlib.sha1(f"{dataset_id}?{urlencode(sorted(q.items()))}".encode()).hexdigest()[:16]
    cache = RAW / f"{dataset_id}-{key}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    headers = {"X-App-Token": TOKEN} if TOKEN else {}
    for attempt in range(4):
        r = requests.get(f"https://{domain}/resource/{dataset_id}.json", params=q, headers=headers, timeout=120)
        if r.status_code == 200:
            cache.write_text(r.text)
            return r.json()
        time.sleep(2 ** attempt)
    r.raise_for_status()


def columns(dataset_id):
    r = requests.get(f"https://data.cityofnewyork.us/api/views/{dataset_id}.json", timeout=60)
    r.raise_for_status()
    return [(c["fieldName"], c["dataTypeName"]) for c in r.json().get("columns", [])]
