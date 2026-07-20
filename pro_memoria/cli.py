"""PM-1 CLI entry point (installed as `pm1-trace`).

Delegates to the real implementation in opencode_plugin/cli.py.
"""

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from opencode_plugin.cli import main
