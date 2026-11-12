"""One error type for every way an exported prediction model is refused."""


class PredictionModelError(ValueError):
    """A prediction model file or setting was refused. The model is not used (fail closed)."""
