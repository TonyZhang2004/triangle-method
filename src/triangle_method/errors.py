"""Exceptions raised for unsupported Triangle Method inputs."""


class PolynomialInputError(ValueError):
    """Report a malformed or unsupported exact polynomial input."""


class PrimitiveInputError(ValueError):
    """Report parameters that do not define a supported nonnegative primitive."""


class CertificateInputError(ValueError):
    """Report malformed decomposition certificate data or incompatible components."""
