"""Heuristic comparison between a public ORCID name and the PDF page text."""

from __future__ import annotations

import csv
import re
import unicodedata
from pathlib import Path

import pymupdf


BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "orcid_input_pdfs"
OUTPUT_DIR = BASE_DIR / "outputs"
TRANSLATION = str.maketrans({"ı":"i", "İ":"i", "ş":"s", "Ş":"s", "ğ":"g", "Ğ":"g", "ü":"u", "Ü":"u", "ö":"o", "Ö":"o", "ç":"c", "Ç":"c"})


def normalize_text(value: str) -> list[str]:
    value = unicodedata.normalize("NFKD", value.translate(TRANSLATION).casefold())
    value = "".join(char for char in value if not unicodedata.combining(char))
    return [token for token in re.findall(r"[a-z0-9]+", value) if len(token) > 1]


def name_match_status(api_name: str, page_text: str) -> tuple[str, str]:
    name_tokens, page_tokens = normalize_text(api_name), set(normalize_text(page_text))
    if not api_name.strip(): return "public_name_missing", "ORCID kaydında kamuya açık ad yok."
    if len(name_tokens) < 2: return "insufficient_api_name", "API adı karşılaştırma için yeterli değil."
    normalized_name = " ".join(name_tokens)
    normalized_page = " ".join(normalize_text(page_text))
    surname, given = name_tokens[-1], name_tokens[:-1]
    if normalized_name in normalized_page: return "exact_name_match", "API adı PDF metninde aynı sırayla bulundu."
    if surname in page_tokens and all(token in page_tokens for token in given): return "token_name_match", "Ad ve soyad tokenları PDF sayfasında bulundu."
    if surname in page_tokens and any(token in page_tokens for token in given): return "probable_name_match", "Soyad ve en az bir ad tokenı PDF sayfasında bulundu."
    if surname in page_tokens: return "surname_only", "Yalnız soyad bulundu; tek başına yeterli kanıt değil."
    return "no_name_match", "API adı ORCID'nin bulunduğu PDF sayfasında bulunamadı."


def main() -> None:
    candidates_file, api_file = OUTPUT_DIR / "orcid_candidates.csv", OUTPUT_DIR / "orcid_api_validation.csv"
    if not candidates_file.exists() or not api_file.exists(): raise SystemExit("Önce ilk iki ORCID aşamasını çalıştır.")
    with candidates_file.open(encoding="utf-8", newline="") as file: candidates = [row for row in csv.DictReader(file) if row["checksum_valid"].lower() == "true"]
    with api_file.open(encoding="utf-8", newline="") as file: api = {row["orcid"]: row for row in csv.DictReader(file)}
    results = []
    for candidate in candidates:
        record = api.get(candidate["orcid"], {}); name = record.get("public_name", "")
        if record.get("api_status") != "found": status, explanation = f"api_{record.get('api_status', 'not_queried')}", "API kaydı bulunmadığı için eşleştirme yapılmadı."
        else:
            document = pymupdf.open(INPUT_DIR / candidate["pdf"])
            text = document[int(candidate["page"]) - 1].get_text("text", sort=True); document.close()
            status, explanation = name_match_status(name, text)
        results.append({"pdf":candidate["pdf"], "page":candidate["page"], "orcid":candidate["orcid"], "orcid_public_name":name, "name_match_status":status, "explanation":explanation})
    fields = ["pdf", "page", "orcid", "orcid_public_name", "name_match_status", "explanation"]
    with (OUTPUT_DIR / "orcid_author_name_matches.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields); writer.writeheader(); writer.writerows(results)
    print(f"Ad eşleşmeleri: {OUTPUT_DIR / 'orcid_author_name_matches.csv'}")


if __name__ == "__main__":
    main()
