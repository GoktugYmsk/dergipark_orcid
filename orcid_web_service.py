"""Temporary request-scoped ORCID analysis for the web interface."""

from __future__ import annotations

import time
from collections import Counter
from pathlib import Path

import pymupdf

from orcid_api_validation import REQUEST_DELAY_SECONDS, lookup_orcid
from orcid_author_matching import name_match_status
from orcid_pilot import find_orcids_in_links, find_orcids_in_text


POSITIVE_MATCHES = {"exact_name_match", "token_name_match", "probable_name_match"}


def analyze_pdf_files(files: list[tuple[Path, str]]) -> dict:
    """Analyze temporary PDF files and return one JSON-safe web response."""
    candidates: list[dict] = []
    page_texts: dict[tuple[str, int], str] = {}
    file_results: list[dict] = []

    for pdf_path, display_name in files:
        candidate_count = 0
        try:
            document = pymupdf.open(pdf_path)
            seen: set[tuple[int, str]] = set()
            for page_number, page in enumerate(document, start=1):
                page_text = page.get_text("text", sort=True)
                page_texts[(display_name, page_number)] = page_text
                page_rows = find_orcids_in_links(display_name, page_number, page)
                for block_index, block in enumerate(page.get_text("blocks", sort=True)):
                    x0, y0, x1, y1, text, *_ = block
                    page_rows.extend(
                        find_orcids_in_text(
                            display_name,
                            page_number,
                            str(text),
                            (x0, y0, x1, y1),
                            block_index,
                        )
                    )
                for row in page_rows:
                    # Linked ORCIDs often also appear in text: present one result.
                    key = (page_number, row["orcid"])
                    if key in seen:
                        continue
                    seen.add(key)
                    candidates.append(row)
                    candidate_count += 1
            page_count = len(document)
            document.close()
            file_results.append(
                {
                    "pdf": display_name,
                    "status": "analyzed",
                    "pages": page_count,
                    "candidate_count": candidate_count,
                    "message": "Analiz tamamlandı." if candidate_count else "ORCID adayı bulunamadı.",
                }
            )
        except Exception as error:
            file_results.append(
                {
                    "pdf": display_name,
                    "status": "pdf_error",
                    "pages": 0,
                    "candidate_count": 0,
                    "message": f"PDF açılamadı: {error}",
                }
            )

    api_cache: dict[str, dict] = {}
    unique_valid_orcids = sorted({row["orcid"] for row in candidates if row["checksum_valid"]})
    for index, orcid in enumerate(unique_valid_orcids, start=1):
        api_cache[orcid] = lookup_orcid(orcid, token=None)
        if index < len(unique_valid_orcids):
            time.sleep(REQUEST_DELAY_SECONDS)

    results: list[dict] = []
    for candidate in candidates:
        api = api_cache.get(candidate["orcid"], {})
        api_status = api.get("api_status", "checksum_invalid")
        api_name = api.get("public_name", "")
        if not candidate["checksum_valid"]:
            status = "checksum_invalid"
            explanation = "ORCID checksum değeri geçersiz olduğu için API sorgusu yapılmadı."
        elif api_status != "found":
            status = f"api_{api_status}"
            explanation = "ORCID kaydı bulunmadığı veya ORCID servisine erişilemediği için ad eşleştirmesi yapılmadı."
        else:
            status, explanation = name_match_status(
                api_name,
                page_texts.get((candidate["pdf"], candidate["page"]), ""),
            )
        results.append(
            {
                "pdf": candidate["pdf"],
                "page": candidate["page"],
                "orcid": candidate["orcid"],
                "source": candidate["source"],
                "checksum_valid": candidate["checksum_valid"],
                "api_status": api_status,
                "orcid_public_name": api_name,
                "name_match_status": status,
                "explanation": explanation,
                "orcid_context": candidate["context"],
                "page_text_excerpt": " ".join(
                    page_texts.get((candidate["pdf"], candidate["page"]), "").split()
                )[:600],
            }
        )

    status_counts = Counter(row["name_match_status"] for row in results)
    summary = {
        "uploaded_pdfs": len(files),
        "analyzed_pdfs": sum(row["status"] == "analyzed" for row in file_results),
        "candidates": len(candidates),
        "checksum_valid": sum(row["checksum_valid"] for row in candidates),
        "api_found": sum(1 for result in api_cache.values() if result["api_status"] == "found"),
        "positive_matches": sum(row["name_match_status"] in POSITIVE_MATCHES for row in results),
        "not_found": status_counts["no_name_match"],
    }
    return {"summary": summary, "file_results": file_results, "results": results}
