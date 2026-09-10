# chi760e-h2o2-analyzer — Stage 5.1.2

当前开发状态：**Stage 5.1.2（单窗口多工作区 GUI session 管理）**。

本阶段提供严格校验的 CH Instruments CHI760E 二进制解析基础设施。parser 只读取原始数据，不进行平滑、基线校正、归一化、统计分析或绘图。

## 当前支持范围

- Linear Sweep Voltammetry（`LSV`）
- Amperometric i-t Curve（`i-t`）

当前已使用 1 个真实 LSV 文件和 1 个真实 i-t 文件进行 regression validation。

Stage 2.5 进一步使用 42 个正式 LSV 文件完成批量兼容性验证：42/42 均通过，实验参数全部一致，且参数块到数据区的距离均为 600 bytes。正式实验 `.bin` 仅在临时工作区读取，没有加入仓库；仓库中的 `batch_validation.csv` 和 `batch_validation_report.md` 只包含文件名、哈希、结构参数、QC 状态和诊断，不包含原始电流数组。

暂不支持、也不会猜测解析：

- CV
- CA
- 其他 CHI 实验类型

当前不能保证兼容所有 CHI 软件版本或文件变体。遇到未知或不符合已验证结构的文件时，parser 会失败并返回结构化诊断信息。

## 解析原则

1. 严格识别长度前缀中的实验类型名称。
2. 动态定位已验证的实验参数块。
3. 点数必须存在相互一致的重复字段。
4. 根据 `data_start = file_size - N × 4` 定位尾部电流数组，并与参数块相对布局交叉验证。
5. 电流按 little-endian IEEE 754 float32 读取，内部原始单位始终为 A。
6. 所有数组保持未平滑、未四舍五入、未改变符号，并标记为只读。
7. NaN、Inf、明显错误的数量级、截断、点数歧义和未知实验类型都会被拒绝。

LSV 的设置终止电位与实际最后采样电位分别保存。例如当前样本配置终点为 `+0.200 V`，400 个采样点实际到达 `+0.199 V`。

i-t 时间轴从一个采样间隔开始，即 `t[i] = (i + 1) × dt`。设置运行时间与实际记录时长分别保存；提前结束只产生 warning。

## 数据模型与后续扩展

`LSVData` 和 `ITData` 暴露 NumPy 数值数组，可直接交给后续 pandas、Matplotlib 和统计模块：

- `potential_V` / `time_s`
- `current_A`
- 文件路径与 SHA-256
- CHI 原始实验参数
- 数据区位置与编码
- validation status、warnings 和 structured diagnostics

用户分组、electrode type、sample ID 和 notes 使用独立的可选 `UserMetadata`，不与 CHI 原始 metadata 混合。`parse_files()` 可批量调用任意文件路径，不依赖固定样本名或目录。

parser、analysis、plotting、export 和未来 GUI 保持职责分离。

批量兼容性检查使用 `validate_lsv_batch()`。每个文件独立处理，一个损坏或不支持的文件不会中止后续文件；结果可通过 `write_batch_validation_csv()` 和 `write_batch_validation_report()` 输出为不含电流数组的验证报告。

## Stage 3 LSV 分析

PB42 preset 的 `run_lsv_analysis()` 对已确认的 42 文件实验设计执行完整且可追踪的分析。分析电位不是固定值；默认 `0.000 V`，也可由调用方设置为扫描范围内的任意电位。精确采样点直接读取，非采样电位使用左右相邻真实点线性插值，禁止外推。

```python
from analysis import AnalysisSettings
from presets.pb42 import run_lsv_analysis

run = run_lsv_analysis(
    "/path/to/42_lsv_files",
    output_base="results",
    settings=AnalysisSettings(
        target_potential_V=-0.050,
        analysis_metric="magnitude",  # 或 "signed"
        bootstrap_seed=20260910,
        bootstrap_resamples=5000,
    ),
)
```

分组信息属于用户 metadata，与 CHI 原始 metadata 分开保存。当前实验布局根据目录和文件名推断 A/B/C、Bare/Material 和 sample ID，并在统计前严格确认每组恰好 `1 Bare + 13 Material`；无法唯一分类时拒绝分析。Bare 只用于原始曲线和逐文件汇总，Material 才进入描述统计和组间检验。

每次运行创建新的时间戳结果目录，不覆盖旧分析。输出包括：

- 42 份保留原始精度与符号的解析 CSV，以及 manifest、参数、指定电位、组汇总、统计、异常值和排除日志 CSV
- `LSV_analysis.xlsx`，包含 `Analysis_Settings`、`File_Metadata`、`Experiment_Parameters`、`Selected_Potential_Data`、`Group_Summary`、`Statistics`、`Outlier_Flags` 和 `Exclusion_Log`
- 原始 LSV、Material mean ± SD、A/B/C overlay、指定电位散点和 CV% 图，每图导出 PNG（300 dpi）、SVG 和 PDF
- 带 source SHA-256、分组、分析电位、metric、统计方法和软件版本的 JSON 分析日志

默认主指标为指定电位处的绝对电流幅值，但 signed current 始终同时保留。分析不会平滑、基线校正、归一化、改变整条曲线符号、自动寻找最显著电位或自动删除 MAD 标记点。正式比较固定为 A–B 和 B–C；A–C 仅标记为 exploratory。

Stage 3.1 增加指定电位电流方向一致性 QC。程序使用明确记录的 `1e-12 A` near-zero tolerance，分别统计 A、B、C 和全部 39 根 Material electrodes 的正、负和近零电流数量。magnitude 模式下若任一组同时存在明显正、负电流，分析继续执行，但会提示绝对值可能掩盖电流方向反转，并要求检查 signed-current 结果。该 QC 不删除样本、不改变原始电流，也不参与已有统计计算。

Stage 3 仍不包括 GUI、i-t 校准分析或 Windows 打包。

## Stage 4 i-t 阶梯加样与校准

Stage 4 使用已经验证的 `ITData`，但把加样时间和最终 H2O2 浓度严格作为用户 metadata。正式分析必须传入 `user_confirmed=True` 的 `StepProtocol`；程序不会根据电流阶跃自动猜测浓度。

```python
from pathlib import Path
from analysis import (
    ITAnalysisInput,
    ITAnalysisSettings,
    StepDefinition,
    StepProtocol,
    run_it_analysis,
)

protocol = StepProtocol(
    user_confirmed=True,
    source="lab notebook",
    steps=(
        StepDefinition("baseline", 0.0, 0.1, True, "0 µM baseline"),
        StepDefinition("step_1", 2.0, 100.0, True),
        StepDefinition("step_2", 5.0, 200.0, True),
        StepDefinition("step_3", 10.0, 300.0, True),
        StepDefinition("step_4", 25.0, 400.0, False, "Excluded from selected linear range"),
    ),
)

run_it_analysis(
    [ITAnalysisInput(Path("electrode_1.bin"), "E1", protocol)],
    settings=ITAnalysisSettings(
        analysis_metric="signed",  # 或 "magnitude"
        plateau_fraction=0.20,
    ),
)
```

区间采用 `[start, end)`，最后区间包含记录末点。平台默认使用每段最后 20% 的真实数据点，比例可配置；短于首选 10 s 的平台只产生 warning，不会向前扩展窗口。平台保存 mean、SD、SEM 和线性 drift。响应严格定义为 `ΔI = I_step - I_baseline`，magnitude 为 `abs(ΔI)`，不会使用 `abs(I_step) - abs(I_baseline)`。

线性范围完全由每个 step 的 `include_in_calibration` 决定。校准使用 ordinary least squares，输出 slope、intercept、R² 和实际纳入浓度。没有足够独立 blank replicates 时明确输出 `LOD not calculated`。多电极结果保留 individual responses，同时汇总每个浓度的 mean、SD、SEM 和 CV%；MAD 和混合 ΔI 方向仅标记，不自动剔除。

`suggest_addition_times()` 仅根据相邻滑动窗口均值变化返回 `Suggested only / 未确认` 的候选时间，不返回浓度，也不修改或平滑用于平台计算的原始电流。候选时间必须由用户确认并组成 StepProtocol 后才能进入正式校准。

Stage 4 不包含 GUI、Windows exe、机器学习或 CV/CA parser。

## Stage 4.5 LSV 通用实验模式

当前 42 文件实验由可选模块 `presets.pb42` 中的 `CURRENT_PB_42_TEMPLATE` 明确定义。PB42 入口 `analyze_lsv_files()` 仍执行目录/文件名识别、A/B/C 严格设计校验、每组 `1 Bare + 13 Material`、A-B/B-C primary comparisons 和 A-C exploratory comparison。该 preset 继续复现 Stage 3/3.1 的数值结果。

新的 Generic LSV Mode 不限定 group 名称、组数、每组 Material 数量或 Bare 是否存在。正式分析接收不可变且由用户确认的 `ExperimentManifest`；自动识别结果只能作为 GUI metadata table 的初始建议，不能绕过用户确认直接统计。

```python
from analysis import (
    AnalysisSettings,
    ComparisonDefinition,
    ManifestEntry,
    confirmed_generic_manifest,
    analyze_lsv_with_manifest,
)

manifest = confirmed_generic_manifest(
    [
        ManifestEntry(
            file_name="electrode_01.bin",
            relative_path="Control/electrode_01.bin",
            group="Control",
            electrode_type="Material",
            sample_id="C01",
            file_path="/data/Control/electrode_01.bin",
        ),
        # 其余经用户核对的文件……
    ],
    source="GUI metadata table confirmation",
)

comparisons = (
    ComparisonDefinition(
        left_group="Control",
        right_group="PB10",
        role="primary: prespecified treatment comparison",
        holm_family="primary_efficacy",
    ),
)

result = analyze_lsv_with_manifest(
    manifest,
    comparisons=comparisons,
    settings=AnalysisSettings(target_potential_V=-0.050),
)
```

Generic Mode 只执行用户声明的 comparisons，不自动进行全组两两比较。Holm adjustment 仅在相同 `holm_family` 中声明的 primary Welch comparisons 之间进行。Bare 保留在逐文件数据和原始曲线中，但不进入 Material 描述统计、outlier QC 或显著性检验。已有的 signed/magnitude、插值、MAD 标记和 current sign QC 科研规则保持不变。

GUI 预留流程为：选择文件 → parser → metadata 建议表 → 用户编辑 → 用户确认 manifest → 设置分析电位和 comparisons → 正式分析。i-t GUI 应自动生成 baseline row：`concentration = 0 µM`，`addition_time = ITData.actual_first_time_s`；用户只输入非零浓度的真实加样时刻。Stage 4.5 不实现 GUI。

## Stage 4.6 可选 preset 与 technique 扩展

Generic LSV core 不导入 `presets.pb42`，也不依赖 PB42 的组名、样本数、文件名或 comparison 定义。新代码应显式从 `presets.pb42` 导入 PB42 功能；未来删除该 preset 不需要修改 `analyze_lsv_with_manifest()` 或 `run_lsv_analysis_with_manifest()`。

`infer_experiment_manifest()` 仅作为 backward-compatible、PB42-specific legacy alias 保留，并会产生 deprecation warning。README 不把它作为 Generic Mode 入口，未来 Generic GUI 也不得调用它；推荐流程始终是 `suggest_generic_manifest()` → 用户核对和编辑 → `confirmed_generic_manifest()`。

`route_for_experiment_type()` 为未来 GUI 提供小型 technique routing contract：当前只路由 LSV 和 i-t。CV 与 CA 尚未实现，不能被强行送入 LSV 分析。未来 CV/CA 可以复用 generic metadata、通用统计、export 和 plotting utilities，但必须有 technique-specific parser 与 analysis logic。尤其 CV 中同一 potential 可在不同 cycle、segment 和 sweep direction 重复出现，因此未来 current-at-potential API 必须显式区分这些维度，不能复用 LSV 的单调电位轴假设。

## Stage 5.1 中文 GUI 基础

Stage 5.1 建立基于 Python `tkinter + ttk` 的中文桌面框架。用户可以选择单个或多个 `.bin` 文件，也可以选择文件夹并递归发现 `.bin`；文件只读解析，不移动、不重命名、不覆盖。每个文件独立处理，一个失败文件不会阻止其他文件。

启动方式：

```bash
python -m chi_gui
```

主窗口提供主页、LSV、i-t、CV 和 CA 导航。LSV 与 i-t 根据 `route_for_experiment_type()` 分流，并显示文件状态、点数、主要实验参数、warning/error 以及内存中的 raw curve preview。LSV 预览使用 `potential_V/current_A`，i-t 预览使用 `time_s/current_A`；电流仅在显示时换算为 µA，不平滑、不校正基线、不归一化、不改变符号，也不写入 `results/`。

CV/CA 当前明确标记为尚未支持，不会路由到 LSV/i-t。Generic GUI 启动和数据加载不 import `presets.pb42`；未来只有用户主动选择 PB42 实验预设时才允许 lazy import。

批量解析通过后台线程执行，worker 只向 thread-safe queue 写入事件，Tk widgets 始终由主线程更新。界面显示进度、批次计数和中文错误摘要，并允许查看技术异常名称与结构化 parser diagnostics。

Stage 5.1 尚未提供 LSV 正式 metadata/statistics workflow，也未提供 i-t Step Protocol/calibration workflow；这些将在后续 GUI 阶段接入已有且经过测试的科研后端，不会在 GUI 中重新实现统计公式。

## Stage 5.1.1 Windows preview / usability patch

GUI 启动时会为 Matplotlib preview 配置系统字体：Windows 优先使用 `Microsoft YaHei`、`Microsoft YaHei UI` 或 `SimHei`，其他系统依次尝试已安装的 CJK 字体并安全回退到 `DejaVu Sans`。项目不捆绑字体文件；`axes.unicode_minus=False` 保证所选中文字体下负号仍可显示。

LSV 与 i-t 页面现在分别自动叠加该 technique 下全部已成功解析的文件，不需要先点击表格。两种 technique 始终使用不同 preview collection，绝不混在同一坐标轴。表格选中项只改变曲线加粗/highlight 和右侧参数内容，不隐藏其他曲线。

右侧紧凑曲线列表使用 session 内稳定颜色显示文件名，并允许临时切换 preview visibility。颜色、选中和可见性都属于 GUI display state，不会改变原始数组、文件 membership、confirmed manifest、outlier/exclusion 或任何科研计算。移除和清空操作同步刷新 preview，但仍不删除磁盘文件。

为避免超长 i-t 曲线拖慢屏幕刷新，preview 绘制超过 5000 点时使用均匀显示级 downsampling，并保留首末点；完整 `time_s`、`potential_V` 和 `current_A` 始终保留在 parser 对象中，正式 analysis 不使用 downsampled 数据。

## Stage 5.1.2 Multi-workspace GUI

单一 MainWindow 顶部提供浏览器式工作区标签：`[工作区 1 ×] [工作区 2 ×] [+]`。首次启动自动创建“工作区 1”；用户可以新建、切换、双击重命名和关闭工作区。关闭包含数据的工作区需要确认，只释放 GUI session state，绝不删除原始文件。当前暂不在程序重启后恢复 session。

每个 Workspace 独立保存 imported/parsed file state、当前 technique 页面、每个页面的 selected file、preview visibility、稳定颜色映射和用户可见日志。切换标签会立即重载该工作区自己的文件表、曲线、曲线列表、参数和日志；移除及清空只作用于当前工作区。同一路径在单个工作区内去重，但允许在多个独立工作区中分别使用。

后台解析任务携带创建任务时的 workspace ID；即使用户解析期间切换标签，结果仍只写回原工作区。正在执行解析任务的工作区在任务结束前不可关闭，避免产生失控 worker 或错误归属。

**Workspace 与科研 Group 严格不同：**Workspace 是一批独立数据/分析会话，不参与统计定义；Group 是 Stage 5.2 confirmed manifest 中的科研分组。未来一个 Workspace 可以包含多个 Groups，GUI 不会把工作区名称自动转换为 Group。

## 安装与测试

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
pytest
```

## Regression samples

真实样本位于 `sample_data/`，测试只读使用，不覆盖或重新保存。

SHA-256：

- LSV：`f505c45e21eabb955c39148359ece2684a459fecc55314ac1c29e257a48e37fb`
- i-t：`c3022e4a26f5c66f7f59746b47bb6c563f68d40f29f7044d3ddaa324b5fcf3f5`

仓库原 `sample/` 文件显示的 40 位值是 Git blob SHA-1，不是 SHA-256；`sample_data/` 中的字节内容与原文件一致。
