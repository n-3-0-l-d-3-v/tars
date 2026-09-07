"""Make the src/ package importable without an editable install, so
`pytest` (and TARS's `tars test`) works immediately after `tars new`."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
