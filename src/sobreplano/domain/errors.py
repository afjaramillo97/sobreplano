"""Domain-level exceptions."""


class DomainValidationError(ValueError):
    """Raised when a domain entity is built with values that break its invariants."""


class FetchError(Exception):
    """Raised when a page cannot be fetched: network error, timeout, redirects or robots.txt."""


class PageParseError(Exception):
    """Raised when an in-scope page lacks a structured field the parser needs (canonical, map)."""


class DuplicateObservationError(Exception):
    """Raised by a repository when the unit type already has an observation that day."""
