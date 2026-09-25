"""Derivative-lineage errors."""

from __future__ import annotations


class DerivativeError(Exception):
    """Base for every error this module raises."""


class DerivativeAlreadyExists(DerivativeError):
    """This anchor already has a native for that destination."""


class DerivativeAlreadyPromoted(DerivativeError):
    """Promote was called on an artifact that is already a top-level Piece."""


class DerivativeNotFound(DerivativeError, KeyError):
    """The artifact id does not resolve, or does not belong to the named anchor."""
