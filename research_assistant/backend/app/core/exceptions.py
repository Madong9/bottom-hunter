class ResearchError(Exception):
    """Base domain exception."""


class StockNotFoundError(ResearchError):
    """Raised when no supported stock can be resolved from a question."""


class TaskNotFoundError(ResearchError):
    """Raised when a research task does not exist."""


class DataProviderError(ResearchError):
    """Raised when a real market-data source is unavailable or incomplete."""


class ConfigurationError(ResearchError):
    """Raised when local runtime configuration is invalid."""
