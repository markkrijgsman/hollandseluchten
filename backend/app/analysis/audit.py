"""The audit trail: an ordered list of the steps taken for one request."""


class AuditLog:
    def __init__(self) -> None:
        self.steps: list[dict] = []

    def log(self, action: str, **detail) -> None:
        self.steps.append({"step": len(self.steps) + 1, "action": action, **detail})
