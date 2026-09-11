"""Chinese desktop GUI orchestration for validated CHI760E backends."""

from .controller import GUIController
from .cursor import (
    CursorReading,
    CursorReadingSet,
    InspectionCursorState,
    build_cursor_readings,
    read_cursor_value,
)
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
    "CursorReading",
    "CursorReadingSet",
    "FileRecord",
    "FileStatus",
    "GUIController",
    "InspectionCursorState",
    "PreviewCollection",
    "PreviewData",
    "PreviewDisplayState",
    "WorkspaceManager",
    "WorkspaceSession",
    "build_cursor_readings",
    "read_cursor_value",
]
