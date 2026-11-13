class NoDataError(Exception):
    """No usable data for the request. `audit` holds the steps taken up to that point."""

    def __init__(self, message: str, audit: list[dict]):
        super().__init__(message)
        self.audit = audit
