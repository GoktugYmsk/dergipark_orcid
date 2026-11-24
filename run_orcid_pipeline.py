"""Run the three file-based ORCID pilot stages in order."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


def main() -> None:
    for script in ("orcid_pilot.py", "orcid_api_validation.py", "orcid_author_matching.py"):
        subprocess.run([sys.executable, str(BASE_DIR / script)], check=True, cwd=BASE_DIR)
    print("ORCID pipeline tamamlandı.")


if __name__ == "__main__":
    main()
