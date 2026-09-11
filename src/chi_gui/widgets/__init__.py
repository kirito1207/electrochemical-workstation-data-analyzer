"""Reusable ttk widgets for the desktop GUI."""

from .curve_list import CurveList
from .file_table import FileTable
from .it_analysis import ITResultPlotPanel, ITResultsPanel, ITSettingsPanel
from .log_panel import LogPanel
from .lsv_analysis import LSVResultPlotPanel, LSVResultsPanel, LSVSettingsPanel
from .plot_preview import PlotPreview
from .workspace_tabs import WorkspaceTabs

__all__ = ["CurveList", "FileTable", "ITResultPlotPanel", "ITResultsPanel",
           "ITSettingsPanel", "LogPanel", "LSVResultPlotPanel", "LSVResultsPanel",
           "LSVSettingsPanel", "PlotPreview", "WorkspaceTabs"]
