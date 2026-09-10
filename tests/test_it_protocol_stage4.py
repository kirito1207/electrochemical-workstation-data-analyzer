from __future__ import annotations

import pytest

from analysis import StepDefinition, StepProtocol, StepProtocolError


def test_step_protocol_requires_strictly_increasing_times(synthetic_it_protocol):
    protocol = StepProtocol(
        user_confirmed=True,
        steps=(
            StepDefinition("baseline", 0.0, 1.0),
            StepDefinition("s1", 2.0, 31.0),
            StepDefinition("s2", 5.0, 31.0),
        ),
    )

    with pytest.raises(StepProtocolError, match="strictly increasing"):
        protocol.validate(recording_start_s=1.0, recording_end_s=120.0)


def test_step_protocol_rejects_addition_outside_recording():
    protocol = StepProtocol(
        user_confirmed=True,
        steps=(
            StepDefinition("baseline", 0.0, 1.0),
            StepDefinition("s1", 2.0, 121.0),
        ),
    )

    with pytest.raises(StepProtocolError, match="recorded time range"):
        protocol.validate(recording_start_s=1.0, recording_end_s=120.0)


def test_concentrations_are_fully_user_configurable():
    concentrations = (0.0, 2.0, 5.0, 10.0, 25.0, 50.0)
    protocol = StepProtocol(
        user_confirmed=True,
        steps=tuple(
            StepDefinition(f"s{index}", concentration, 1.0 + index * 10.0)
            for index, concentration in enumerate(concentrations)
        ),
    )

    protocol.validate(recording_start_s=1.0, recording_end_s=60.0)
    assert tuple(step.concentration_uM for step in protocol.steps) == concentrations


def test_unconfirmed_protocol_cannot_enter_formal_analysis(synthetic_it_data, synthetic_it_protocol):
    protocol = StepProtocol(
        steps=synthetic_it_protocol.steps,
        user_confirmed=False,
        source="suggested candidates",
    )

    with pytest.raises(StepProtocolError, match="user_confirmed=True"):
        protocol.validate(
            recording_start_s=synthetic_it_data.actual_first_time_s,
            recording_end_s=synthetic_it_data.actual_last_time_s,
        )


def test_step_protocol_can_be_loaded_from_csv(tmp_path):
    path = tmp_path / "step_protocol.csv"
    path.write_text(
        "step_id,concentration_uM,addition_time_s,include_in_calibration,notes\n"
        "baseline,0,1,true,blank\n"
        "s1,3.5,31,false,user excluded\n",
        encoding="utf-8",
    )

    protocol = StepProtocol.from_csv(path, user_confirmed=True)

    assert protocol.steps[1].concentration_uM == 3.5
    assert not protocol.steps[1].include_in_calibration
    assert protocol.source == str(path)
