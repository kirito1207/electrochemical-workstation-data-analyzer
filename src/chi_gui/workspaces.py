"""Headless multi-workspace session management.

A Workspace is a GUI data/analysis session. It is intentionally unrelated to
the scientific Group metadata used by formal LSV analysis.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .cursor import InspectionCursorState
from .state import AppState, PreviewDisplayState


def _default_selection() -> dict[str, str | None]:
    return {"all": None, "LSV": None, "i-t": None, "CV": None, "CA": None}


def _default_cursors() -> dict[str, InspectionCursorState]:
    return {"LSV": InspectionCursorState(), "i-t": InspectionCursorState()}


@dataclass(slots=True)
class WorkspaceSession:
    workspace_id: str
    name: str
    state: AppState = field(default_factory=AppState)
    preview_display: PreviewDisplayState = field(default_factory=PreviewDisplayState)
    selected_by_route: dict[str, str | None] = field(default_factory=_default_selection)
    cursor_by_route: dict[str, InspectionCursorState] = field(default_factory=_default_cursors)
    current_route: str = "all"
    log_messages: list[str] = field(default_factory=list)

    def clear_data(self) -> None:
        """Clear only this GUI session; never delete source files."""

        self.state.clear()
        self.preview_display = PreviewDisplayState()
        self.selected_by_route = _default_selection()
        self.cursor_by_route = _default_cursors()


class WorkspaceManager:
    """Ordered independent sessions for one operating-system MainWindow."""

    def __init__(self) -> None:
        self._sessions: dict[str, WorkspaceSession] = {}
        self._sequence = 0
        first = self.create()
        self._active_id = first.workspace_id

    @property
    def sessions(self) -> tuple[WorkspaceSession, ...]:
        return tuple(self._sessions.values())

    @property
    def active(self) -> WorkspaceSession:
        return self._sessions[self._active_id]

    def get(self, workspace_id: str) -> WorkspaceSession | None:
        return self._sessions.get(workspace_id)

    def create(self, name: str | None = None) -> WorkspaceSession:
        self._sequence += 1
        workspace_id = f"workspace-{self._sequence}"
        session = WorkspaceSession(
            workspace_id=workspace_id,
            name=(name.strip() if name and name.strip() else f"工作区 {self._sequence}"),
        )
        self._sessions[workspace_id] = session
        self._active_id = workspace_id
        return session

    def switch(self, workspace_id: str) -> WorkspaceSession:
        if workspace_id not in self._sessions:
            raise KeyError(f"Unknown workspace: {workspace_id}")
        self._active_id = workspace_id
        return self.active

    def rename(self, workspace_id: str, name: str) -> None:
        cleaned = name.strip()
        if not cleaned:
            raise ValueError("工作区名称不能为空。")
        session = self._sessions.get(workspace_id)
        if session is None:
            raise KeyError(f"Unknown workspace: {workspace_id}")
        session.name = cleaned

    def close(self, workspace_id: str) -> WorkspaceSession:
        if workspace_id not in self._sessions:
            raise KeyError(f"Unknown workspace: {workspace_id}")
        ids = list(self._sessions)
        index = ids.index(workspace_id)
        removed = self._sessions.pop(workspace_id)
        if not self._sessions:
            self.create()
        elif self._active_id == workspace_id:
            remaining = list(self._sessions)
            self._active_id = remaining[min(index, len(remaining) - 1)]
        return removed


__all__ = ["WorkspaceManager", "WorkspaceSession"]
