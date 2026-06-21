"""Deterministic label print automation package."""

from .states import (
    STATUS_ASSIGNED,
    STATUS_DOWNLOADING,
    STATUS_FAILED,
    STATUS_PRINTING,
    STATUS_QUEUED,
    STATUS_RENDERING,
    STATUS_SUCCESS,
)
from .version import APP_VERSION as __version__

__all__ = [
    "STATUS_ASSIGNED",
    "STATUS_DOWNLOADING",
    "STATUS_FAILED",
    "STATUS_PRINTING",
    "STATUS_QUEUED",
    "STATUS_RENDERING",
    "STATUS_SUCCESS",
    "__version__",
]
