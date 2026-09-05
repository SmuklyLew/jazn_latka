from __future__ import annotations


class PackGeneratorError(RuntimeError):
    """Base error reported to every Jaźń Pack Generator interface."""


class PackValidationError(PackGeneratorError):
    """Invalid source, destination, profile or archive member."""


class PackSafetyError(PackGeneratorError):
    """Operation rejected because it could escape the declared safety boundary."""


class PackCancelled(PackGeneratorError):
    """Long running operation was cancelled by the operator."""


class PackIntegrityError(PackGeneratorError):
    """Created or supplied package failed integrity verification."""
