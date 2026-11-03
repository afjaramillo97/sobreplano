"""Hand-kept project coordinates, the last resort when a page publishes no map link."""

from sobreplano.domain.catalog import GeoPoint

# Keyed by project slug. Each entry is validated by GeoPoint at import time, so a point
# outside the Aburrá Valley stops the scraper from starting. Every entry needs a comment
# with the source URL and the review date, so anyone can check it again:
#
#     # https://maps.app.goo.gl/... (sales room on the project's public map), reviewed 2026-11-02
#     "some-project": GeoPoint(lat=6.2731, lon=-75.5871),
MANUAL_LOCATIONS: dict[str, GeoPoint] = {}
