"""Run all local ORCID pilot stages in the correct order."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
STEPS = (
    ("1/3 ORCID çıkarımı ve checksum kontrolü", "orcid_pilot.py"),
    ("2/3 ORCID Public API kayıt doğrulaması", "orcid_api_validation.py"),
    ("3/3 ORCID adı ile PDF metni eşleştirmesi", "orcid_author_matching.py"),
)


def main() -> None:
    for description, script_name in STEPS:
        print("\n" + "=" * 68)
        print(description)
        print("=" * 68)
        subprocess.run([sys.executable, str(BASE_DIR / script_name)], check=True, cwd=BASE_DIR)

    print("\nORCID pipeline tamamlandı.")
    print(f"Ana rapor: {BASE_DIR / 'outputs' / 'orcid_author_name_report.txt'}")


if __name__ == "__main__":
    main()
