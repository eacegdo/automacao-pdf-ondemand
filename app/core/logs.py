import logging

_ICONS = {logging.WARNING: "⚠ ", logging.ERROR: "✗ ", logging.CRITICAL: "✗ "}


class _Formatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        record.icon = _ICONS.get(record.levelno, "")
        return super().format(record)


def setup_logging() -> None:
    """Uma linha por passo: `14:02:11 │ Login: OK (2.1s)`."""
    handler = logging.StreamHandler()
    handler.setFormatter(_Formatter("%(asctime)s │ %(icon)s%(message)s", datefmt="%H:%M:%S"))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
