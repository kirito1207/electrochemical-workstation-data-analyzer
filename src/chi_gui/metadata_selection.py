"""Headless selection state used by the LSV metadata Treeview."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass(slots=True)
class MetadataSelectionModel:
    ordered_keys: tuple[str, ...] = ()
    selected: set[str] = field(default_factory=set)
    anchor: str | None = None
    press_key: str | None = None
    press_y: int = 0
    drag_active: bool = False
    drag_threshold_px: int = 4

    def reset(self, keys: Iterable[str], selected: Iterable[str] = ()) -> None:
        self.ordered_keys = tuple(keys)
        available = set(self.ordered_keys)
        self.selected = {key for key in selected if key in available}
        self.anchor = self.anchor if self.anchor in available else None
        self.press_key = None
        self.drag_active = False

    def click(self, key: str, *, ctrl: bool = False, shift: bool = False) -> tuple[str, ...]:
        if key not in self.ordered_keys:
            return self.selection()
        if shift and self.anchor in self.ordered_keys:
            ranged = set(self.range_between(self.anchor, key))
            self.selected = self.selected | ranged if ctrl else ranged
        elif ctrl:
            if key in self.selected:
                self.selected.remove(key)
            else:
                self.selected.add(key)
            self.anchor = key
        else:
            self.selected = {key}
            self.anchor = key
        return self.selection()

    def begin_drag(self, key: str, y: int, selected: Iterable[str] = ()) -> None:
        self.selected = {item for item in selected if item in self.ordered_keys}
        self.press_key = key if key in self.ordered_keys else None
        self.press_y = int(y)
        self.drag_active = False

    def drag_to(self, key: str, y: int) -> tuple[str, ...] | None:
        if self.press_key is None or key not in self.ordered_keys:
            return None
        if not self.drag_active and abs(int(y) - self.press_y) < self.drag_threshold_px:
            return None
        self.drag_active = True
        self.selected = set(self.range_between(self.press_key, key))
        return self.selection()

    def finish_drag(self) -> bool:
        dragged = self.drag_active
        if dragged and self.press_key is not None:
            self.anchor = self.press_key
        self.press_key = None
        self.drag_active = False
        return dragged

    def select_all(self) -> tuple[str, ...]:
        self.selected = set(self.ordered_keys)
        if self.ordered_keys:
            self.anchor = self.ordered_keys[0]
        return self.selection()

    def clear(self) -> tuple[str, ...]:
        self.selected.clear()
        return ()

    def range_between(self, first: str, last: str) -> tuple[str, ...]:
        start = self.ordered_keys.index(first)
        stop = self.ordered_keys.index(last)
        low, high = sorted((start, stop))
        return self.ordered_keys[low : high + 1]

    def selection(self) -> tuple[str, ...]:
        return tuple(key for key in self.ordered_keys if key in self.selected)


__all__ = ["MetadataSelectionModel"]
