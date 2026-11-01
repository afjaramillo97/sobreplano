"""Unit tests for the composition root: bad configuration fails before any I/O."""

import pytest

from sobreplano.infrastructure.settings import Settings
from sobreplano.interface.composition import ConfigurationError, run_scrape

# Never reached: every case fails before the engine is created.
URL = "postgresql+psycopg://postgres:postgres@127.0.0.1:1/postgres"


@pytest.mark.parametrize(
    ("settings", "developer"),
    [
        (Settings(database_url=URL), "otra-constructora"),
        (Settings(database_url=URL, extraction_model="gpt-6-luna"), "londono-gomez"),
        (Settings(database_url=URL, raw_store="s3://bucket/prefix"), "londono-gomez"),
    ],
)
def test_bad_configuration_raises_before_any_io(settings: Settings, developer: str) -> None:
    with pytest.raises(ConfigurationError):
        run_scrape(settings, developer, limit=None, dry_run=True)
