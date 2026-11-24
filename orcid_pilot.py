"""Local ORCID extraction and checksum-validation pilot.

This component is intentionally independent from detect_language.py. It reads
every PDF placed in orcid_input_pdfs/ and creates a CSV audit trail plus a plain-text
report. No external ORCID service or credentials are needed at this stage.
"""

from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from pathlib import Path

import pymupdf


BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "orcid_input_pdfs"
OUTPUT_DIR = BASE_DIR / "outputs"

# Captures either a complete ORCID URL or an identifier written as bare text.
ORCID_PATTERN = re.compile(
    r"(?<![\w-])(?:(?:https?://)?(?:www\.)?orcid\.org/)?"
    r"(?P<orcid>\d{4}-\d{4}-\d{4}-\d{3}[\dXx])(?![\w-])",
    flags=re.IGNORECASE,
)


def normalize_orcid(value: str) -> str:
    """Return a canonical 0000-0000-0000-000X representation."""
    compact = re.sub(r"[^0-9Xx]", "", value).upper()
    if len(compact) != 16:
        return value.strip().upper()
    return "-".join((compact[:4], compact[4:8], compact[8:12], compact[12:]))


def checksum_is_valid(orcid: str) -> bool:
    """Validate an ORCID iD using the ISO/IEC 7064 MOD 11-2 checksum."""
    compact = orcid.replace("-", "").upper()
    if not re.fullmatch(r"\d{15}[\dX]", compact):
        return False
    total = 0
    for digit in compact[:15]:
        total = (total + int(digit)) * 2
    check_value = (12 - (total % 11)) % 11
    expected = "X" if check_value == 10 else str(check_value)
    return compact[-1] == expected


def make_row(
    pdf_name: str,
    page_number: int,
    source: str,
    matched_text: str,
    orcid: str,
    bbox: tuple[float, float, float, float] | None,
    context: str,
) -> dict:
    return {
        "pdf": pdf_name,
        "page": page_number,
        "source": source,
        "matched_text": matched_text,
        "orcid": orcid,
        "format_valid": bool(re.fullmatch(r"\d{4}-\d{4}-\d{4}-\d{3}[\dX]", orcid)),
        "checksum_valid": checksum_is_valid(orcid),
        "x0": round(bbox[0], 1) if bbox else "",
        "y0": round(bbox[1], 1) if bbox else "",
        "x1": round(bbox[2], 1) if bbox else "",
        "y1": round(bbox[3], 1) if bbox else "",
        "context": " ".join(context.split())[:500],
    }


def find_orcids_in_text(
    pdf_name: str, page_number: int, text: str, block_bbox: tuple[float, float, float, float], block_index: int
) -> list[dict]:
    rows: list[dict] = []
    for match in ORCID_PATTERN.finditer(text):
        found = match.group(0)
        orcid = normalize_orcid(match.group("orcid"))
        start = max(0, match.start() - 180)
        end = min(len(text), match.end() + 220)
        rows.append(
            make_row(
                pdf_name, page_number, f"text_block_{block_index}", found, orcid, block_bbox, text[start:end]
            )
        )
    return rows


def find_orcids_in_links(pdf_name: str, page_number: int, page: pymupdf.Page) -> list[dict]:
    rows: list[dict] = []
    for link in page.get_links():
        uri = link.get("uri") or ""
        match = ORCID_PATTERN.search(uri)
        if not match:
            continue
        rect = link.get("from")
        bbox = (rect.x0, rect.y0, rect.x1, rect.y1) if rect else None
        rows.append(
            make_row(
                pdf_name,
                page_number,
                "pdf_link",
                uri,
                normalize_orcid(match.group("orcid")),
                bbox,
                f"PDF bağlantısı: {uri}",
            )
        )
    return rows


def main() -> None:
    pdf_files = sorted(INPUT_DIR.glob("*.pdf"))
    if not pdf_files:
        raise SystemExit("orcid_input_pdfs klasöründe PDF bulunamadı.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    per_pdf: dict[str, Counter] = defaultdict(Counter)

    for pdf_path in pdf_files:
        document = pymupdf.open(pdf_path)
        seen: set[tuple[int, str, str]] = set()
        for page_number, page in enumerate(document, start=1):
            page_rows = find_orcids_in_links(pdf_path.name, page_number, page)
            for block_index, block in enumerate(page.get_text("blocks", sort=True)):
                x0, y0, x1, y1, text, *_ = block
                page_rows.extend(
                    find_orcids_in_text(
                        pdf_path.name, page_number, str(text), (x0, y0, x1, y1), block_index
                    )
                )
            for row in page_rows:
                key = (page_number, row["orcid"], row["source"])
                if key in seen:
                    continue
                seen.add(key)
                rows.append(row)
                per_pdf[pdf_path.name]["candidates"] += 1
                per_pdf[pdf_path.name]["checksum_valid"] += int(row["checksum_valid"])
        document.close()

    fieldnames = [
        "pdf", "page", "source", "matched_text", "orcid", "format_valid",
        "checksum_valid", "x0", "y0", "x1", "y1", "context",
    ]
    csv_file = OUTPUT_DIR / "orcid_candidates.csv"
    with csv_file.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    valid = sum(int(row["checksum_valid"]) for row in rows)
    unique_valid = len({row["orcid"] for row in rows if row["checksum_valid"]})
    report_lines = [
        "YEREL ORCID ÇIKARIM VE CHECKSUM DOĞRULAMA RAPORU",
        "=" * 62,
        "Kapsam: PDF metni ve PDF içindeki URI bağlantıları tarandı.",
        "Bu aşamada ORCID API'ye istek yapılmadı; kayıt/yazar adı doğrulaması sonraki aşamadır.",
        "",
    ]
    for pdf_path in pdf_files:
        stats = per_pdf[pdf_path.name]
        report_lines.extend(
            [
                f"{pdf_path.name}",
                f"  Bulunan aday: {stats['candidates']}",
                f"  Checksum geçerli: {stats['checksum_valid']}",
            ]
        )
        pdf_rows = [row for row in rows if row["pdf"] == pdf_path.name]
        if not pdf_rows:
            report_lines.append("  ORCID bulunamadı.")
        else:
            for row in pdf_rows:
                validity = "geçerli" if row["checksum_valid"] else "GEÇERSİZ"
                report_lines.extend(
                    [
                        f"  - Sayfa {row['page']} | ORCID: {row['orcid']} | {validity} | kaynak: {row['source']}",
                        f"    Bağlam: {row['context']}",
                    ]
                )
        report_lines.append("")
    report_lines.extend(
        [
            "GENEL SONUÇ",
            "-" * 62,
            f"Taranan PDF: {len(pdf_files)}",
            f"Toplam ORCID aday kaydı: {len(rows)}",
            f"Checksum geçerli aday: {valid}",
            f"Tekil ve checksum geçerli ORCID: {unique_valid}",
            "",
            "Not: Checksum geçerliliği ORCID numarasının yapısal olarak tutarlı olduğunu",
            "gösterir. ORCID kaydının gerçekten varlığı ve kayıt sahibinin PDF yazarıyla",
            "eşleşmesi, sonraki API tabanlı doğrulama aşamasında ölçülecektir.",
        ]
    )
    report_file = OUTPUT_DIR / "orcid_local_report.txt"
    report_file.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    print(f"ORCID adayları: {csv_file}")
    print(f"Okunabilir rapor: {report_file}")


if __name__ == "__main__":
    main()
