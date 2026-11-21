"""Ścieżki importu dla testów analysis, niezależnie od katalogu uruchomienia.

Testy działają zarówno z `analysis/` (konfiguracja w pyproject.toml), jak i z głównego
katalogu repozytorium (pytest.ini: testpaths = backend analysis), gdzie `analysis/src`
nie jest na ścieżce. Bez tego `import prawdowid_analysis` zawodzi przy zbieraniu testów.
"""

import sys
from pathlib import Path

ANALYSIS_DIR = Path(__file__).resolve().parents[1]
for path in (ANALYSIS_DIR / "src", ANALYSIS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
