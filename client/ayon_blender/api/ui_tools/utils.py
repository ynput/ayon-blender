from .communication import IPCHandler


def show_message(title: str, message: str, level: str = "warning") -> None:
    IPCHandler.execute(
        "generic",
        "show_message",
        dict(
            title=title,
            message=message,
            level=level,
        )
    )
