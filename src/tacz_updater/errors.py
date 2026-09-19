class TaczUpdaterError(Exception):
    """Base class for expected, user-facing errors."""


class ConfigError(TaczUpdaterError):
    pass


class CredentialError(TaczUpdaterError):
    pass


class ApiError(TaczUpdaterError):
    def __init__(self, code: str, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class PackError(TaczUpdaterError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code

