"""Human-readable GUI formatting without changing backend values."""

from __future__ import annotations

from chi_parser import ITData, LSVData


def format_voltage(value: float) -> str:
    return f"{value:.3f} V"


def format_scan_rate(value_V_s: float) -> str:
    return f"{value_V_s * 1000:.3g} mV/s"


def format_increment(value_V: float) -> str:
    return f"{value_V * 1000:.3g} mV"


def format_seconds(value: float) -> str:
    return f"{value:.1f} s"


def format_current_uA(value_A: float) -> str:
    return f"{value_A * 1e6:.3f} µA"


def primary_parameter_text(data: LSVData | ITData | None) -> str:
    if isinstance(data, LSVData):
        return (
            f"{format_voltage(data.configured_start_potential_V)} → "
            f"{format_voltage(data.configured_final_potential_V)}；"
            f"{format_scan_rate(data.scan_rate_V_s)}"
        )
    if isinstance(data, ITData):
        return (
            f"E = {format_voltage(data.applied_potential_V)}；"
            f"Δt = {format_seconds(data.sample_interval_s)}"
        )
    return "—"


def parameter_rows(data: LSVData | ITData | None) -> tuple[tuple[str, str], ...]:
    if isinstance(data, LSVData):
        return (
            ("实验类型", "Linear Sweep Voltammetry (LSV)"),
            ("数据点数", str(data.n_points)),
            ("起始电位", format_voltage(data.configured_start_potential_V)),
            ("设置终止电位", format_voltage(data.configured_final_potential_V)),
            ("实际末点电位", format_voltage(data.actual_last_potential_V)),
            ("扫描速率", format_scan_rate(data.scan_rate_V_s)),
            ("电位间隔", format_increment(data.potential_increment_V)),
            ("校验状态", data.validation_status),
        )
    if isinstance(data, ITData):
        return (
            ("实验类型", "Amperometric i-t Curve"),
            ("数据点数", str(data.n_points)),
            ("工作电位", format_voltage(data.applied_potential_V)),
            ("采样间隔", format_seconds(data.sample_interval_s)),
            ("设置运行时间", format_seconds(data.configured_run_time_s)),
            ("实际起始时间", format_seconds(data.actual_first_time_s)),
            ("实际末点时间", format_seconds(data.actual_last_time_s)),
            ("校验状态", data.validation_status),
        )
    return ()
