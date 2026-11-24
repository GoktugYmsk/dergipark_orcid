"""ORCID Public API lookup stage for checksum-valid candidates."""

from __future__ import annotations

import csv
import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "outputs"
REQUEST_DELAY_SECONDS = 0.25
PERSON_URL = "https://pub.orcid.org/v3.0/{orcid}/person"


def public_name(payload: dict) -> str:
    name = payload.get("name") or {}
    credit = (name.get("credit-name") or {}).get("value")
    if credit:
        return credit
    given = (name.get("given-names") or {}).get("value", "").strip()
    family = (name.get("family-name") or {}).get("value", "").strip()
    return " ".join(value for value in (given, family) if value)


def lookup_orcid(orcid: str, token: str | None = None) -> dict:
    headers = {"Accept": "application/vnd.orcid+json"}
    if token or os.environ.get("ORCID_ACCESS_TOKEN"):
        headers["Authorization"] = f"Bearer {token or os.environ['ORCID_ACCESS_TOKEN']}"
    try:
        with urlopen(Request(PERSON_URL.format(orcid=orcid), headers=headers), timeout=30) as response:
            return {"api_status": "found", "http_status": 200, "public_name": public_name(json.load(response)), "api_error": ""}
    except HTTPError as error:
        return {"api_status": "not_found" if error.code == 404 else "api_error", "http_status": error.code, "public_name": "", "api_error": str(error.reason)}
    except URLError as error:
        return {"api_status": "network_error", "http_status": "", "public_name": "", "api_error": str(error.reason)}


def main() -> None:
    candidates_file = OUTPUT_DIR / "orcid_candidates.csv"
    if not candidates_file.exists():
        raise SystemExit("Önce `python orcid_pilot.py` çalıştır.")
    with candidates_file.open(encoding="utf-8", newline="") as file:
        candidates = [row for row in csv.DictReader(file) if row["checksum_valid"].lower() == "true"]
    results = []
    for index, orcid in enumerate(sorted({row["orcid"] for row in candidates}), 1):
        print(f"[{index}] ORCID sorgulanıyor: {orcid}")
        results.append({"orcid": orcid, **lookup_orcid(orcid)})
        if index < len({row["orcid"] for row in candidates}): time.sleep(REQUEST_DELAY_SECONDS)
    with (OUTPUT_DIR / "orcid_api_validation.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["orcid", "api_status", "http_status", "public_name", "api_error"]); writer.writeheader(); writer.writerows(results)
    print(f"API sonuçları: {OUTPUT_DIR / 'orcid_api_validation.csv'}")


if __name__ == "__main__":
    main()
