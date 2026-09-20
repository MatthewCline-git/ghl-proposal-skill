class SpecError(ValueError):
    """The spec Claude wrote is wrong. Nothing was touched; fix it and rerun."""


class SetupError(RuntimeError):
    """The account isn't set up for this (e.g. the proposal template is missing)."""


class VerifyError(RuntimeError):
    """GHL said yes but the thing that exists is not what we asked for."""
