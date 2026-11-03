import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]

from helpers import SESSION_ROWS, write_session  # noqa: E402
from importer import import_data  # noqa: E402
from laps import mark_pace_laps  # noqa: E402


@pytest.fixture(scope="session")
def marked(tmp_path_factory):
    """Sesión sintética (3 coches) ya importada y con vueltas clasificadas."""
    path = write_session(tmp_path_factory.mktemp("data") / "session.csv", SESSION_ROWS)
    return mark_pace_laps(import_data(path))