"""Errors reported by experimental figure inspection tools."""


class AuditInputError(ValueError):
    """The supplied figure or options cannot be safely inspected."""


class UnknownSpacingRole(KeyError):
    """A requested spacing role is absent from the observation set."""
