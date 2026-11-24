"""Batch ORCID extraction and checksum validation for local pilot PDFs."""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path

import pymupdf


BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "orcid_input_pdfs"
OUTPUT_DIR = BASE_DIR / "outputs"
ORCID_PATTERN = re.compile(
    r"(?<![\w-])(?:(?:https?://)?(?:www\.)?orcid\.org/)?"
    r"(?P<orcid>\d{4}-\d{4}-\d{4}-\d{3}[\dXx])(?![\w-])",
    re.IGNORECASE,
)


def normalize_orcid(value: str) -> str:
    compact = re.sub(r"[^0-9Xx]", "", value).upper()
    return "-".join((compact[:4], compact[4:8], compact[8:12], compact[12:])) if len(compact) == 16 else value.strip().upper()


def checksum_is_valid(orcid: str) -> bool:
    compact = orcid.replace("-", "").upper()
    if not re.fullmatch(r"\d{15}[\dX]", compact):
        return False
    total = 0
    for digit in compact[:15]:
        total = (total + int(digit)) * 2
    expected = "X" if (12 - total % 11) % 11 == 10 else str((12 - total % 11) % 11)
    return compact[-1] == expected


def make_row(pdf_name: str, page_number: int, source: str, matched_text: str, orcid: str, bbox, context: str) -> dict:
    return {
        "pdf": pdf_name, "page": page_number, "source": source, "matched_text": matched_text,
        "orcid": orcid, "format_valid": bool(re.fullmatch(r"\d{4}-\d{4}-\d{4}-\d{3}[\dX]", orcid)),
        "checksum_valid": checksum_is_valid(orcid),
        "x0": round(bbox[0], 1) if bbox else "", "y0": round(bbox[1], 1) if bbox else "",
        "x1": round(bbox[2], 1) if bbox else "", "y1": round(bbox[3], 1) if bbox else "",
        "context": " ".join(context.split())[:500],
    }


def find_orcids_in_text(pdf_name: str, page_number: int, text: str, block_bbox, block_index: int) -> list[dict]:
    rows = []
    for match in ORCID_PATTERN.finditer(text):
        start, end = max(0, match.start() - 180), min(len(text), match.end() + 220)
        rows.append(make_row(pdf_name, page_number, f"text_block_{block_index}", match.group(0), normalize_orcid(match.group("orcid")), block_bbox, text[start:end]))
    return rows


def find_orcids_in_links(pdf_name: str, page_number: int, page: pymupdf.Page) -> list[dict]:
    rows = []
    for link in page.get_links():
        uri = link.get("uri") or ""
        match = ORCID_PATTERN.search(uri)
        if match:
            rect = link.get("from")
            bbox = (rect.x0, rect.y0, rect.x1, rect.y1) if rect else None
            rows.append(make_row(pdf_name, page_number, "pdf_link", uri, normalize_orcid(match.group("orcid")), bbox, f"PDF bağlantısı: {uri}"))
    return rows


def main() -> None:
    pdf_files = sorted(INPUT_DIR.glob("*.pdf"))
    if not pdf_files:
        raise SystemExit("orcid_input_pdfs klasöründe PDF bulunamadı.")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rows, stats = [], defaultdict(int)
    for pdf_path in pdf_files:
        document = pymupdf.open(pdf_path)
        seen = set()
        for number, page in enumerate(document, 1):
            page_rows = find_orcids_in_links(pdf_path.name, number, page)
            for block_index, block in enumerate(page.get_text("blocks", sort=True)):
                x0, y0, x1, y1, text, *_ = block
                page_rows.extend(find_orcids_in_text(pdf_path.name, number, str(text), (x0, y0, x1, y1), block_index))
            for row in page_rows:
                key = (number, row["orcid"])
                if key not in seen:
                    seen.add(key); rows.append(row); stats[pdf_path.name] += 1
        document.close()
    fields = ["pdf", "page", "source", "matched_text", "orcid", "format_valid", "checksum_valid", "x0", "y0", "x1", "y1", "context"]
    with (OUTPUT_DIR / "orcid_candidates.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    report = ["YEREL ORCID ÇIKARIM RAPORU", "=" * 44, f"Taranan PDF: {len(pdf_files)}", f"Toplam aday: {len(rows)}", f"Checksum geçerli: {sum(row['checksum_valid'] for row in rows)}", ""]
    report.extend(f"{name}: {count} aday" for name, count in stats.items())
    (OUTPUT_DIR / "orcid_local_report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"ORCID adayları: {OUTPUT_DIR / 'orcid_candidates.csv'}")


if __name__ == "__main__":
    main()
