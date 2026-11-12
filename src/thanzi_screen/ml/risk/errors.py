"""One error type for every way a risk model or its data can be refused."""


class RiskModelError(ValueError):
    """A risk model file, dataset or setting was refused. The model is not used (fail closed)."""
