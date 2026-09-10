"""Chinese desktop GUI orchestration for validated CHI760E backends."""

from .controller import GUIController
from .state import (
    AppState,
    FileRecord,
    FileStatus,
    PreviewCollection,
    PreviewData,
    PreviewDisplayState,
)
from .workspaces import WorkspaceManager, WorkspaceSession

__version__ = "0.1.0"

__all__ = [
    "AppState",
    "FileRecord",
    "FileStatus",
    "GUIController",
    "PreviewCollection",
    "PreviewData",
    "PreviewDisplayState",
    "WorkspaceManager",
    "WorkspaceSession",
]
