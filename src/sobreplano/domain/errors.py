"""Domain-level exceptions."""


class DomainValidationError(ValueError):
    """Raised when a domain entity is built with values that break its invariants."""
