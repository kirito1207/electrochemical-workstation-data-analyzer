"""Named LSV experiment designs kept separate from generic analysis logic."""

from __future__ import annotations

from dataclasses import dataclass

from .statistics import ComparisonDefinition


@dataclass(frozen=True, slots=True)
class GroupDesign:
    group: str
    description: str
    expected_bare: int
    expected_material: int


@dataclass(frozen=True, slots=True)
class PB42ExperimentTemplate:
    name: str
    groups: tuple[GroupDesign, ...]
    comparisons: tuple[ComparisonDefinition, ...]

    @property
    def group_order(self) -> tuple[str, ...]:
        return tuple(item.group for item in self.groups)


CURRENT_PB_42_TEMPLATE = PB42ExperimentTemplate(
    name="CURRENT_PB_42_TEMPLATE",
    groups=(
        GroupDesign("A", "PB 10 cycles; water; 100 µM H2O2", 1, 13),
        GroupDesign("B", "PB 10 cycles; PBS; 100 µM H2O2", 1, 13),
        GroupDesign("C", "PB 20 cycles; PBS; 100 µM H2O2", 1, 13),
    ),
    comparisons=(
        ComparisonDefinition(
            left_group="A",
            right_group="B",
            role="primary: detection medium (water vs PBS), PB 10 cycles",
            holm_family="pb42_primary",
        ),
        ComparisonDefinition(
            left_group="B",
            right_group="C",
            role="primary: PB deposition cycles (10 vs 20), PBS",
            holm_family="pb42_primary",
        ),
        ComparisonDefinition(
            left_group="A",
            right_group="C",
            role="exploratory: medium and PB cycles both differ",
        ),
    ),
)


__all__ = [
    "CURRENT_PB_42_TEMPLATE",
    "GroupDesign",
    "PB42ExperimentTemplate",
]
