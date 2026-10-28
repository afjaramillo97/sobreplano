"""The price observation repository exposes no way to change history (constitution, principle 2)."""

from sobreplano.infrastructure.db.price_observation_repository import (
    SqlPriceObservationRepository,
)


def test_repository_has_no_update_or_delete() -> None:
    assert not hasattr(SqlPriceObservationRepository, "update")
    assert not hasattr(SqlPriceObservationRepository, "delete")
