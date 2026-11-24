"""Vercel Python endpoint for one temporary ORCID PDF-analysis request."""

from __future__ import annotations

import json
import re
import sys
import tempfile
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from orcid_web_service import analyze_pdf_files  # noqa: E402


MAX_FILES = 10
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 40 * 1024 * 1024
SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._ -]+")


def reply(request: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request.send_response(status)
    request.send_header("Content-Type", "application/json; charset=utf-8")
    request.send_header("Content-Length", str(len(body)))
    request.end_headers()
    request.wfile.write(body)


def safe_name(value: str, index: int) -> str:
    name = Path(value or f"belge_{index}.pdf").name
    name = SAFE_FILENAME.sub("_", name).strip(". ") or f"belge_{index}.pdf"
    return name if name.lower().endswith(".pdf") else f"{name}.pdf"


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_type = self.headers.get("Content-Type", "")
            content_length = int(self.headers.get("Content-Length", "0"))
            if "multipart/form-data" not in content_type:
                reply(self, 400, {"detail": "İstek multipart/form-data biçiminde olmalıdır."})
                return
            if content_length <= 0 or content_length > MAX_TOTAL_BYTES + 1024 * 1024:
                reply(self, 413, {"detail": "Toplam yükleme sınırı 40 MB."})
                return

            raw_body = self.rfile.read(content_length)
            message = BytesParser(policy=default).parsebytes(
                f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8") + raw_body
            )
            uploads = []
            for part in message.iter_parts():
                if part.get_content_disposition() != "form-data":
                    continue
                if part.get_param("name", header="content-disposition") != "files":
                    continue
                filename = part.get_filename() or ""
                content = part.get_payload(decode=True) or b""
                uploads.append((filename, content))

            if not uploads:
                reply(self, 400, {"detail": "En az bir PDF yüklenmelidir."})
                return
            if len(uploads) > MAX_FILES:
                reply(self, 400, {"detail": "En fazla 10 PDF yüklenebilir."})
                return

            with tempfile.TemporaryDirectory(prefix="orcid-analysis-") as directory:
                files = []
                total_size = 0
                for index, (filename, content) in enumerate(uploads, start=1):
                    if not filename.lower().endswith(".pdf"):
                        reply(self, 400, {"detail": f"{filename}: yalnızca PDF kabul edilir."})
                        return
                    if len(content) > MAX_FILE_BYTES:
                        reply(self, 413, {"detail": f"{filename}: tek dosya sınırı 8 MB."})
                        return
                    total_size += len(content)
                    if total_size > MAX_TOTAL_BYTES:
                        reply(self, 413, {"detail": "Toplam yükleme sınırı 40 MB."})
                        return
                    display_name = safe_name(filename, index)
                    path = Path(directory) / f"{index}_{display_name}"
                    path.write_bytes(content)
                    files.append((path, display_name))
                reply(self, 200, analyze_pdf_files(files))
        except Exception as error:
            print(f"ORCID analysis error: {error}", file=sys.stderr)
            reply(self, 500, {"detail": "Analiz sırasında sunucu hatası oluştu."})
