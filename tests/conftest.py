import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def pytest_configure(config):
    # R21: `make test` runs -m "not slow"; `make test-all` runs everything.
    config.addinivalue_line(
        "markers", "slow: heavy assembly clash checks and full regenerations (make test-all)")
