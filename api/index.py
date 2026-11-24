"""Vercel-compatible API for temporary ORCID analysis uploads."""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from orcid_web_service import analyze_pdf_files  # noqa: E402


MAX_FILES = 10
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 40 * 1024 * 1024
SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._ -]+")

app = FastAPI(title="ORCID Doğrulama API")


def safe_name(value: str, index: int) -> str:
    name = Path(value or f"belge_{index}.pdf").name
    name = SAFE_FILENAME.sub("_", name).strip(". ") or f"belge_{index}.pdf"
    return name if name.lower().endswith(".pdf") else f"{name}.pdf"


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "service": "orcid-analysis"}


@app.post("/api/analyze-orcid")
async def analyze_orcid(files: list[UploadFile] = File(...)) -> dict:
    """Analyze up to ten digital PDFs and discard temporary copies afterwards."""
    if not files:
        raise HTTPException(status_code=400, detail="En az bir PDF yüklenmelidir.")
    if len(files) > MAX_FILES:
        raise HTTPException(status_code=400, detail=f"En fazla {MAX_FILES} PDF yüklenebilir.")

    total_bytes = 0
    with tempfile.TemporaryDirectory(prefix="orcid-analysis-") as directory:
        temporary_files: list[tuple[Path, str]] = []
        for index, upload in enumerate(files, start=1):
            original_name = upload.filename or f"belge_{index}.pdf"
            if not original_name.lower().endswith(".pdf"):
                raise HTTPException(status_code=400, detail=f"{original_name}: yalnızca PDF kabul edilir.")
            content = await upload.read()
            if len(content) > MAX_FILE_BYTES:
                raise HTTPException(status_code=413, detail=f"{original_name}: tek dosya sınırı 8 MB.")
            total_bytes += len(content)
            if total_bytes > MAX_TOTAL_BYTES:
                raise HTTPException(status_code=413, detail="Toplam yükleme sınırı 40 MB.")
            display_name = safe_name(original_name, index)
            temporary_path = Path(directory) / f"{index}_{display_name}"
            temporary_path.write_bytes(content)
            temporary_files.append((temporary_path, display_name))

        return await run_in_threadpool(analyze_pdf_files, temporary_files)
