class SonarError(Exception):
    """Base class for exceptions in this module."""

    pass


class SonarAuthenticationError(SonarError):
    """Raised when authentication with SonarCloud fails (401)."""

    pass


class SonarPermissionError(SonarError):
    """Raised when the user does not have permission to access the resource (403)."""

    pass


class SonarResourceNotFoundError(SonarError):
    """Raised when a project or other resource is not found (404)."""

    pass


class SonarValidationError(SonarError):
    """Raised when the API returns a 400 Bad Request with validation errors."""

    def __init__(self, message: str, errors: list[dict[str, str]] | None = None) -> None:
        super().__init__(message)
        self.errors = errors or []


class SonarRateLimitError(SonarError):
    """Raised when the API rate limit is exceeded (429)."""

    pass
