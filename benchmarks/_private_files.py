"""Owner-only benchmark artifacts without importing (and pinning) the product package.

Some benchmarks import a baseline package from another source directory in worker
processes. Loading the self-contained platform helper by path keeps that A/B intact.
"""

import importlib.util
import sys
from pathlib import Path

_NAME = "_jev_benchmark_secure_fs"
_PATH = Path(__file__).resolve().parents[1] / "src" / "apixly_jev_harness" / "_secure_fs.py"


def _load():
    if _NAME not in sys.modules:
        spec = importlib.util.spec_from_file_location(_NAME, _PATH)
        module = importlib.util.module_from_spec(spec)
        sys.modules[_NAME] = module
        spec.loader.exec_module(module)
    return sys.modules[_NAME]


secure_fs = _load()
