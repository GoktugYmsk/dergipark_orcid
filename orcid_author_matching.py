"""Compare ORCID Public API names with likely author text in the source PDF.

Input files are produced by the two earlier, independent components:
  - outputs/orcid_candidates.csv
  - outputs/orcid_api_validation.csv

This is a transparent heuristic, not an identity proof. It compares an API
public name with text on the same PDF page where that ORCID was extracted.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from collections import Counter
from pathlib import Path

import pymupdf


BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "orcid_input_pdfs"
OUTPUT_DIR = BASE_DIR / "outputs"
CANDIDATES_FILE = OUTPUT_DIR / "orcid_candidates.csv"
API_FILE = OUTPUT_DIR / "orcid_api_validation.csv"

TURKISH_TRANSLATION = str.maketrans(
    {"ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g", "ü": "u", "Ü": "u", "ö": "o", "Ö": "o", "ç": "c", "Ç": "c"}
)
STOPWORDS = {"dr", "prof", "doc", "assoc", "phd", "orcid", "org", "http", "https"}


def normalize_text(value: str) -> list[str]:
    """Fold Turkish characters, punctuation and case to comparable word tokens."""
    value = value.translate(TURKISH_TRANSLATION).casefold()
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    tokens = re.findall(r"[a-z0-9]+", value)
    return [token for token in tokens if token not in STOPWORDS and len(token) > 1]


def name_match_status(api_name: str, page_text: str) -> tuple[str, str]:
    """Return a conservative text-match status and an explanation."""
    name_tokens = normalize_text(api_name)
    page_tokens = normalize_text(page_text)
    if not api_name.strip():
        return "public_name_missing", "ORCID kaydında kamuya açık ad yok."
    if len(name_tokens) < 2:
        return "insufficient_api_name", "API adı soyad + ad karşılaştırması için yeterli değil."

    page_token_set = set(page_tokens)
    given_tokens = name_tokens[:-1]
    surname = name_tokens[-1]
    surname_present = surname in page_token_set
    given_present = [token for token in given_tokens if token in page_token_set]
    normalized_name = " ".join(name_tokens)
    normalized_page = " ".join(page_tokens)

    if normalized_name in normalized_page:
        return "exact_name_match", "API adı PDF metninde aynı sırayla bulundu."
    if surname_present and len(given_present) == len(given_tokens):
        return "token_name_match", "Ad ve soyad tokenları PDF sayfasında bulundu."
    if surname_present and given_present:
        return "probable_name_match", "Soyad ve en az bir ad tokenı PDF sayfasında bulundu."
    if surname_present:
        return "surname_only", "Yalnızca soyad bulundu; tek başına yeterli kanıt değil."
    return "no_name_match", "API adı PDF'nin ORCID bulunan sayfasında bulunamadı."


def page_text_for(pdf_path: Path, page_number: int) -> str:
    document = pymupdf.open(pdf_path)
    try:
        if page_number < 1 or page_number > len(document):
            return ""
        return document[page_number - 1].get_text("text", sort=True)
    finally:
        document.close()


def main() -> None:
    if not CANDIDATES_FILE.exists() or not API_FILE.exists():
        raise SystemExit(
            "Önce `python orcid_pilot.py` ve `python orcid_api_validation.py` çalıştır."
        )

    with CANDIDATES_FILE.open(encoding="utf-8", newline="") as file:
        candidates = [row for row in csv.DictReader(file) if row["checksum_valid"].lower() == "true"]
    with API_FILE.open(encoding="utf-8", newline="") as file:
        api_rows = {row["orcid"]: row for row in csv.DictReader(file)}

    results: list[dict] = []
    seen: set[tuple[str, int, str]] = set()
    for candidate in candidates:
        key = (candidate["pdf"], int(candidate["page"]), candidate["orcid"])
        if key in seen:
            continue
        seen.add(key)

        api = api_rows.get(candidate["orcid"], {})
        api_status = api.get("api_status", "not_queried")
        api_name = api.get("public_name", "")
        pdf_path = INPUT_DIR / candidate["pdf"]
        if not pdf_path.exists():
            status, explanation, page_excerpt = "pdf_missing", "PDF dosyası bulunamadı.", ""
        elif api_status != "found":
            status = f"api_{api_status}"
            explanation = "ORCID API kaydı bulunmadığı veya sorgu tamamlanmadığı için ad eşleştirmesi yapılmadı."
            page_excerpt = ""
        else:
            page_text = page_text_for(pdf_path, int(candidate["page"]))
            status, explanation = name_match_status(api_name, page_text)
            page_excerpt = " ".join(page_text.split())[:600]

        results.append(
            {
                "pdf": candidate["pdf"],
                "page": candidate["page"],
                "orcid": candidate["orcid"],
                "api_status": api_status,
                "orcid_public_name": api_name,
                "name_match_status": status,
                "explanation": explanation,
                "orcid_context": candidate["context"],
                "page_text_excerpt": page_excerpt,
            }
        )

    fieldnames = [
        "pdf", "page", "orcid", "api_status", "orcid_public_name", "name_match_status",
        "explanation", "orcid_context", "page_text_excerpt",
    ]
    csv_file = OUTPUT_DIR / "orcid_author_name_matches.csv"
    with csv_file.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    counts = Counter(row["name_match_status"] for row in results)
    verified = counts["exact_name_match"] + counts["token_name_match"] + counts["probable_name_match"]
    report_lines = [
        "ORCID API ADI VE PDF YAZAR METNİ KARŞILAŞTIRMA RAPORU",
        "=" * 66,
        "Yöntem: ORCID API'den gelen kamuya açık ad, ORCID'nin geçtiği PDF sayfasının",
        "metniyle Türkçe karakter normalizasyonu yapılarak karşılaştırıldı.",
        "Bu sonuç otomatik bir aday eşleşmesidir; kimlik kanıtı değildir.",
        "",
    ]
    for row in results:
        report_lines.extend(
            [
                f"PDF: {row['pdf']} | Sayfa: {row['page']}",
                f"  ORCID: {row['orcid']} | API: {row['api_status']}",
                f"  ORCID kamuya açık adı: {row['orcid_public_name'] or '(yok / görünür değil)'}",
                f"  Eşleşme: {row['name_match_status']}",
                f"  Açıklama: {row['explanation']}",
                "",
            ]
        )
    report_lines.extend(
        [
            "GENEL SONUÇ",
            "-" * 66,
            f"Karşılaştırılan PDF-ORCID çifti: {len(results)}",
            f"Otomatik olumlu aday eşleşme: {verified}",
            f"Exact eşleşme: {counts['exact_name_match']}",
            f"Token eşleşmesi: {counts['token_name_match']}",
            f"Muhtemel eşleşme: {counts['probable_name_match']}",
            f"Yalnız soyad: {counts['surname_only']}",
            f"Eşleşme yok: {counts['no_name_match']}",
            f"Kamuya açık ad yok: {counts['public_name_missing']}",
        ]
    )
    report_file = OUTPUT_DIR / "orcid_author_name_report.txt"
    report_file.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    print(f"Ad eşleştirme CSV: {csv_file}")
    print(f"Ad eşleştirme raporu: {report_file}")


if __name__ == "__main__":
    main()
