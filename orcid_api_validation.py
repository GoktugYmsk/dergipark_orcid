"""Validate checksum-valid ORCID candidates against the ORCID Public API.

Reads outputs/orcid_candidates.csv produced by orcid_pilot.py. This script only
checks whether the identifier resolves to a public ORCID record and retrieves a
public display name when available. It does not modify ORCID records.

This component works with ORCID's anonymous read access for a small pilot.
Optional environment variables ORCID_ACCESS_TOKEN or ORCID_CLIENT_ID plus
ORCID_CLIENT_SECRET enable registered /read-public access for larger workloads.
"""

from __future__ import annotations

import csv
import json
import os
import time
from collections import defaultdict
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "outputs"
CANDIDATES_FILE = OUTPUT_DIR / "orcid_candidates.csv"
TOKEN_URL = "https://orcid.org/oauth/token"
PERSON_URL = "https://pub.orcid.org/v3.0/{orcid}/person"
REQUEST_DELAY_SECONDS = 0.25


def get_optional_access_token() -> str | None:
    """Use registered access when supplied; otherwise use anonymous public reads."""
    existing_token = os.environ.get("ORCID_ACCESS_TOKEN")
    if existing_token:
        return existing_token

    client_id = os.environ.get("ORCID_CLIENT_ID")
    client_secret = os.environ.get("ORCID_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None

    payload = urlencode(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
            "scope": "/read-public",
        }
    ).encode("utf-8")
    request = Request(TOKEN_URL, data=payload, method="POST", headers={"Accept": "application/json"})
    with urlopen(request, timeout=30) as response:
        token_payload = json.load(response)
    return token_payload["access_token"]


def public_name(person_payload: dict) -> str:
    name = person_payload.get("name") or {}
    credit = (name.get("credit-name") or {}).get("value")
    if credit:
        return credit
    given = (name.get("given-names") or {}).get("value", "").strip()
    family = (name.get("family-name") or {}).get("value", "").strip()
    return " ".join(part for part in (given, family) if part)


def lookup_orcid(orcid: str, token: str | None) -> dict:
    headers = {"Accept": "application/vnd.orcid+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(PERSON_URL.format(orcid=orcid), headers=headers)
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.load(response)
        name = public_name(payload)
        return {"api_status": "found", "http_status": 200, "public_name": name, "api_error": ""}
    except HTTPError as error:
        status = "not_found" if error.code == 404 else "api_error"
        return {"api_status": status, "http_status": error.code, "public_name": "", "api_error": error.reason}
    except URLError as error:
        return {"api_status": "network_error", "http_status": "", "public_name": "", "api_error": str(error.reason)}


def main() -> None:
    if not CANDIDATES_FILE.exists():
        raise SystemExit("Önce `python orcid_pilot.py` çalıştır; orcid_candidates.csv bulunamadı.")

    with CANDIDATES_FILE.open(encoding="utf-8", newline="") as file:
        candidates = list(csv.DictReader(file))
    valid_candidates = [row for row in candidates if row["checksum_valid"].lower() == "true"]
    unique_orcids = sorted({row["orcid"] for row in valid_candidates})
    if not unique_orcids:
        raise SystemExit("Checksum geçerli ORCID adayı bulunamadı.")

    token = get_optional_access_token()
    source_pdfs: dict[str, set[str]] = defaultdict(set)
    for row in valid_candidates:
        source_pdfs[row["orcid"]].add(row["pdf"])

    results: list[dict] = []
    for index, orcid in enumerate(unique_orcids, start=1):
        print(f"[{index}/{len(unique_orcids)}] ORCID sorgulanıyor: {orcid}")
        result = lookup_orcid(orcid, token)
        results.append({"orcid": orcid, "source_pdfs": "; ".join(sorted(source_pdfs[orcid])), **result})
        if index < len(unique_orcids):
            time.sleep(REQUEST_DELAY_SECONDS)

    csv_file = OUTPUT_DIR / "orcid_api_validation.csv"
    fieldnames = ["orcid", "source_pdfs", "api_status", "http_status", "public_name", "api_error"]
    with csv_file.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    counts = defaultdict(int)
    for result in results:
        counts[result["api_status"]] += 1
    report_lines = [
        "ORCID PUBLIC API DOĞRULAMA RAPORU",
        "=" * 56,
        "Kapsam: checksum geçerli ORCID adayları, ORCID Public API üzerinden",
        "kamuya açık kişi kaydı bulunuyor mu diye sorgulandı.",
        f"Erişim modu: {'registered /read-public' if token else 'anonymous public read'}",
        "",
    ]
    for result in results:
        report_lines.extend(
            [
                f"ORCID: {result['orcid']}",
                f"  API sonucu: {result['api_status']} | HTTP: {result['http_status']}",
                f"  Kamuya açık ad: {result['public_name'] or '(yok / görünür değil)'}",
                f"  Kaynak PDF: {result['source_pdfs']}",
                f"  Hata: {result['api_error']}" if result["api_error"] else "",
                "",
            ]
        )
    report_lines.extend(
        [
            "GENEL SONUÇ",
            "-" * 56,
            f"Sorgulanan tekil ORCID: {len(results)}",
            f"Kayıt bulundu: {counts['found']}",
            f"Kayıt bulunamadı: {counts['not_found']}",
            f"API/ağ hatası: {counts['api_error'] + counts['network_error']}",
            "",
            "Not: found sonucu ORCID kaydının varlığını gösterir. PDF yazarıyla ad",
            "eşleşmesi, bir sonraki aşamada PDF'den yazar adı çıkarılıp ayrıca ölçülmelidir.",
        ]
    )
    report_file = OUTPUT_DIR / "orcid_api_report.txt"
    report_file.write_text("\n".join(line for line in report_lines if line is not None) + "\n", encoding="utf-8")
    print(f"API doğrulama CSV: {csv_file}")
    print(f"API doğrulama raporu: {report_file}")


if __name__ == "__main__":
    main()
