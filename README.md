# Electrochemical Workstation Data Analyzer — Stage 5.3.1.3.1

当前开发状态：**Stage 5.3.1.3.1（Align i-t batch metadata controls with LSV interaction）**。

电化学工作站数据分析软件。当前重点支持并验证 CH Instruments CHI760E 原生 LSV 与 i-t 数据解析、统计分析、可视化和 GUI 工作流。

This is a desktop-oriented electrochemical workstation data analysis project with validated CHI760E binary parsing and Generic LSV/i-t analysis infrastructure.

仓库名称和顶层定位已经泛化，但这不表示 native binary parser 已支持所有厂家的电化学工作站。当前真实文件验证范围仍以 CHI760E 为主；未来架构可以扩展 CV、CA 和其他 technique，但必须先实现并验证各自的 technique-specific parser 与分析逻辑。

parser 只读取原始数据，不进行平滑、基线校正、归一化、统计分析或绘图。

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

Stage 4.5 当时只预留 GUI 流程：选择文件 → parser → metadata 建议表 → 用户编辑 → 用户确认 manifest → 设置分析电位和 comparisons → 正式分析。该阶段未实现 GUI；其早期固定浓度式 i-t 草案后来已由 Stage 5.3/5.3.1 的通用 Event Timeline 设计取代。

## Stage 4.6 可选 preset 与 technique 扩展

Generic LSV core 不导入 `presets.pb42`，也不依赖 PB42 的组名、样本数、文件名或 comparison 定义。新代码应显式从 `presets.pb42` 导入 PB42 功能；未来删除该 preset 不需要修改 `analyze_lsv_with_manifest()` 或 `run_lsv_analysis_with_manifest()`。

历史 PB42 inference 仅保留显式的 `presets.pb42.infer_current_pb42_manifest()`；原 `infer_experiment_manifest()` alias 与 `analysis` 包级 PB42 lazy exports 已删除。Generic Mode 入口始终是 `suggest_generic_manifest()` → 用户核对和编辑 → `confirmed_generic_manifest()`。

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

## Stage 5.1.3 Interactive curve cursor

LSV 和 i-t 原始曲线 preview 支持左键单击设置只读检查游标，并以垂直参考线显示当前位置。右侧现有曲线列表会对全部可见曲线内联显示该位置的 `Current / µA`；隐藏曲线不显示读数，选中文件仍仅控制高亮和实验参数。可使用“清除游标”恢复无游标状态。

LSV 游标读数直接调用已验证的 `extract_current_at_potential()`：命中采样点时读取原始值，位于相邻点之间时线性插值，并禁止外推。i-t 游标使用最近真实采样点，同时在内部保留请求时间和实际采样时间；检查游标不会成为加样时间。所有计算均为只读，不修改 `potential_V`、`time_s` 或 `current_A`。

每个 Workspace 分别保存 LSV 与 i-t 的游标位置和可见状态，切换后恢复各自读数。**Inspection cursor 与正式 analysis target potential 是两个独立概念**：点击 preview 不会改变分析设置、样本纳入、科研 Group 或 exclusion。消息日志默认弱化为紧凑摘要，可按需展开完整诊断。

## Stage 5.1.3.1 Windows responsiveness hotfix

Windows 验收发现，程序化 `Treeview.selection_set()` 可能派发 `<<TreeviewSelect>>`，而选择回调此前会再次执行完整 preview render 并重新设置同一 selection，形成事件递归。当前 `FileTable` 使用 selection-event guard 同时阻止同步和延迟到达的程序化选择事件，并在目标 key 已选中时跳过无意义的 `selection_set()`。`MainWindow` 另有 selected-state 幂等检查，相同 selected key 不再触发曲线列表重建、Matplotlib 重绘或参数刷新。

一次真实用户选择变化只产生一次有效 preview render；导入完成后的首个成功文件仍自动选中，但后续程序化同步不会重新进入用户回调。该修复保留多曲线 preview、LSV/i-t cursor、inline readings、visibility、稳定颜色、Workspace 独立状态和折叠日志，不修改 parser、analysis/statistics、i-t calibration 或任何原始数组。

## Stage 5.1.4 Precise numeric cursor control

右侧曲线列表标题区提供紧凑数值输入框。LSV 输入单位为 V，i-t 输入单位为 s；按 Enter 后与 workspace-local inspection cursor、图中垂直线和所有可见曲线的内联电流读数同步。LSV 任意范围内数值继续复用 extract_current_at_potential()，采样点读取 raw current、点间执行线性插值；i-t 读数使用最近真实采样点，并保留 requested time 与 actual sampled time。

当 plot preview 或游标输入框具有焦点时，←/→ 会移动到前一个或后一个真实 x-axis sample，不假定固定 potential increment 或 sample interval。处于两点之间时分别跳到左右包围采样点，到达边界后保持边界。按键没有进行全局绑定，因此不会影响其他 Entry 或 Text 控件的正常编辑。

空值、非数值、NaN、Inf 或全部可见曲线范围外的输入均采用安静的 inline 状态：隐藏 vertical line、读数显示“—”，并在输入框旁显示简短提示，不弹窗、不写大量错误日志。每个 Workspace 分别保存输入文本、有效 cursor value、visible state 和提示。该 inspection cursor 仍不连接 analysis target potential、i-t StepProtocol、样本 inclusion 或统计逻辑。

## Stage 5.2 Generic LSV 正式分析 GUI

LSV 页面现提供四个紧凑工作流标签：`数据与曲线`、`分析设置`、`统计结果`、`结果图表`。每个 Workspace 独立保存 LSV metadata 草稿、用户确认的 manifest、分析电位、signed/magnitude 指标、用户声明的 comparisons、分析结果、QC 和结果图选择；Workspace 名称绝不会被自动当作科研 Group。

分析设置表对每个成功解析的 LSV 文件显示并允许编辑 Include、Sample ID、Group、Electrode Type 和 Notes。`suggest_generic_manifest()` 只生成可编辑建议，界面明确标记“尚未确认”；用户必须点击“确认样本信息”，由 `confirmed_generic_manifest()` 建立不可变 manifest 后才能正式统计。Include 与 raw preview visibility 相互独立；Bare 可纳入逐文件输出和 raw curves，但不进入 Material 描述统计、MAD 或显著性检验。当前 GUI 默认全部纳入，MAD 只标记 Possible outlier；手工 exclusion workflow 留待后续独立审计界面实现。

分析电位可直接输入，也可通过显式“使用当前游标电位”按钮从有效 LSV inspection cursor 复制。鼠标或键盘移动 inspection cursor 不会自动修改分析电位。正式分析仅调用现有 `analyze_lsv_with_manifest()` 后端，在 worker thread 中执行；GUI 不重新实现插值、Welch、Mann–Whitney、Holm、Hedges' g、bootstrap CI、MAD 或 current sign QC。

Comparison 只由用户明确添加，并记录 Left Group、Right Group、Primary/Exploratory、Holm Family 和名称。Holm correction 仍仅作用于同一 family 的 primary Welch comparisons。运行前会统一检查 confirmed manifest、included Material、Sample ID、Group、分析电位共同范围、comparison group 与最小样本数；错误以内联中文信息呈现，不启动半完成分析。

统计结果页展示当前 metric 的 group descriptive statistics、Welch/Mann–Whitney、raw/Holm p、mean difference 与 CI、Hedges' g 与 CI、sign QC、MAD 标记和 warning。设置发生变化后，现有结果立即标记为 stale，并在重新分析前禁止导出。结果图表页一次显示一张后端科研图，可切换 raw curves、mean ± SD、mean overlay、selected-potential signed/magnitude scatter 和 CV%。

“导出当前完整分析结果”只导出当前内存中的非过期 result，不会重新分析。每次导出创建新的时间戳目录，不覆盖旧目录。LSV 输出包含 Excel、CSV、PNG 300 dpi、SVG、PDF 和 provenance JSON log；Generic i-t Event 输出包含通用 CSV 与 PNG 300 dpi/SVG/PDF 图。CV/CA/ML 与 Windows exe 仍未实现。

Windows Stage 5.2 人工验收清单见 `docs/windows_stage52_checklist.md`。

## Stage 5.2.1 Generic LSV GUI usability hardening

Stage 5.2 首轮 Windows 验收后的易用性加固已完成。Confirm 与 Run 的失败原因现在直接显示在分析设置页，不再只写入默认折叠日志；重复 `(Group, Sample ID)`、缺失 Group/Sample ID/电极类型会汇总为简洁中文，并显示少量对象预览。成功确认、分析进行中、完成和 stale result 也有明确的 inline feedback 与四步 workflow 状态。

Metadata 表对 included 且必填字段缺失的行使用轻量“未设置”提示。表格支持鼠标上下连续拖选、Ctrl/Shift 原有选择、Ctrl+A、全选和取消选择；拖动超过小阈值才按连续行选择处理，因此普通双击编辑仍保留。批量 Group/电极类型操作只作用于当前 selection，不改变 raw preview visibility 或 Include。

Generic manifest 继续优先保存绝对 `file_path`，允许同一 Workspace 导入多个目录；不同目录同名文件的 `relative_path` 会保留可区分 provenance。Sample ID inference 仍只是可编辑文件名建议，正式分析只使用用户确认后的 `ManifestEntry.sample_id`。

Workspace 切换现在显式重置未提交 comparison editor 草稿及不存在的 Combobox 文本；已点击“添加”的 ComparisonDraft 仍在各自 Workspace 中独立保存。结果页增加分析摘要、中文列名、MAD 无 flag 的明确成功状态，以及 sign QC 正常/mixed 的易读提示。

GUI 的指定电位 magnitude/signed scatter 支持 Material individual point hover，显示用户确认后的 Sample ID 和对应电流。Stage 5.2.1.1 使用显示坐标中的 10 px 最近点命中，避免 TkAgg/Windows 对个别小型 scatter marker 的 artist hit-test 不稳定；边缘点与 S11 等任意 Sample ID 均无特判。Hover 只更新内存 annotation，不重新分析或重建 Figure；Bare、mean marker 和 SD errorbar 不参与 hover。静态 PNG/SVG/PDF 导出继续不增加永久 Sample ID 标签，科研数值与 Stage 3/3.1 完全一致。

Windows Stage 5.2.1 人工验收清单见 `docs/windows_stage521_checklist.md`。i-t 正式 GUI、CV、CA、ML 和 Windows exe 均未进入本阶段。

## Stage 5.2.2 Generic LSV 多 Group 与布局加固

Generic LSV GUI 现由用户确认后的 Material metadata 自动识别 1、2、3 到 N 个 Group，不要求预先声明组数，也不限定 A/B/C 等名称。单 Group 可在没有 comparison 的情况下完成 selected-potential extraction、描述统计、MAD、sign QC 和全部适用科研图；多 Group 仍只执行用户显式添加的任意 pairwise comparisons，不自动穷举所有组合。同一 Primary Holm Family 的 Welch p 校正语义保持不变。

描述统计、selected magnitude/signed scatter、Material mean ± SD、mean overlay 和 repeatability CV% 会覆盖全部 Material Groups。类别图根据 Group 数量与标签长度扩展宽度并在需要时旋转标签；颜色按稳定顺序分配。Raw curves 与 Mean ± SD 的 GUI Group filter 支持 `ALL` 或任一当前 Group。Bare 仍保留在 raw curves，并继续排除在 Material summaries、MAD、sign QC Material counts 和组间检验之外。Hover 继续直接使用 confirmed `ManifestEntry.sample_id` 与对应 signed/magnitude 数值。

数据页使用独立、有左右最小宽度和可恢复 sash fraction 的 `tk.PanedWindow`。切换 workflow tab、窗口 resize 或 Workspace 后会恢复合理比例；结果页的 Treeview/Matplotlib requested geometry 不再参与数据页分栏计算。右侧曲线列表使用有界显示名与首选宽度，完整路径仍可在实验参数/详情中查看，长文件名不会继续撑大右栏。

Stage 5.2.2 没有新增 ANOVA、Welch ANOVA、Kruskal–Wallis、Tukey、Games–Howell 或 Dunn，也没有修改 parser、selected-potential extraction、描述统计公式、pairwise statistics、MAD、sign QC 或 i-t backend。Windows 人工验收清单见 `docs/windows_stage522_checklist.md`。

## Stage 5.2.3 多组整体条件效应统计

当全部已确认且 included 的 Material Groups 达到 3 组或更多时，Generic LSV 正式分析会基于当前 selected-potential 正式指标并列报告 one-way Welch ANOVA 与 Kruskal–Wallis sensitivity analysis。Welch ANOVA 不假设各组等方差；Kruskal–Wallis 回答多组响应分布/rank 的整体差异问题，两者不会互相充当“确认”关系。每组均采用保守的 `n >= 2` policy；不满足、存在非有限值、零组内方差或所有 rank 值完全相同时，会返回带原因的 unavailable 状态而非静默 NaN。

统计结果页新增独立的“整体多组比较”区域，展示 statistic、Welch numerator/denominator df、Kruskal–Wallis df、p-value、状态与说明。1 组或 2 组时会明确显示不适用。整体检验始终使用全部 Material Groups，不提供选择性 group subset；Bare 继续排除。结果导出新增 `omnibus_statistics.csv`、Excel `Omnibus statistics` sheet，并在 provenance JSON 中记录方法和完整结果。

此设计是 additive：原有“分析设置 → 用户定义比较”中的 Left Group、Right Group、Role、Holm Family 和 Name 编辑流程保持不变。用户定义的 pairwise comparisons 始终照常执行，既不会由 omnibus p-value 控制，也不会自动生成所有两两组合；原有 Welch independent-samples t-test、Mann–Whitney、mean difference、bootstrap CI、Hedges' g 和 Holm correction 公式与语义均未修改。Stage 5.2.3 未新增 classical ANOVA、Tukey、Games–Howell、Dunn、paired/repeated-measures 或 mixed-effects models，也未修改 selected plots、parser 或 i-t backend。Windows 人工验收清单见 `docs/windows_stage523_checklist.md`。

## Stage 5.3 Generic i-t Event analysis architecture

i-t 的新 Generic core 使用用户确认的 `EventTimeline`。`Event` 只记录稳定 `event_id`、时间、任意名称、可选数值/单位和 notes；它不等同于 plateau window，也不绑定 addition、dose 或 concentration。默认 baseline 是记录开始至首个 Event 前的 reference segment，后续每个 Event 到下一 Event（最后一个到记录末端）形成独立 response segment。正式均值、SD 与响应始终来自时间窗口；默认 `PlateauPolicy(mode="tail_fraction", fraction=0.20)` 保留末段 20% 规则，也支持用户明确给出的 windows。少于两个真实点或短记录缺少后期 Event 时返回 per-record unavailable，不扩大窗口、不删除整批分析。

`EventResponse` 同时保存 baseline/response mean、SD、n、signed `delta_current_uA = response - baseline` 与 `abs(delta)`。一个共享 Timeline 可用于 1/2/N 个不同长度记录，Sample ID 和 Group 完全由用户定义。Calibration 默认关闭；只有显式 `CalibrationSelection(event_ids, x_label, x_unit)` 才拟合 OLS，并只使用被选且具有 numeric value、完全一致 unit 的 Events，不自动选择 numeric Event、不自动换算单位。Generic CSV 使用 `events.csv`、`response_windows.csv`、`event_responses.csv`、`event_summary.csv`，启用时才生成 `calibration.csv`。

Stage 5.3 建立 backend/API、通用 export 与 event-marker figure。numeric cursor 本身始终只用于 inspection；Stage 5.3.1 GUI 只能通过“从当前游标添加草稿”这一显式动作复制所选曲线的真实采样时间，且 Event Timeline 必须再次由用户确认后才能进入正式分析。自动 event detection、smoothing、baseline correction、固定 Concentration/µM UI、CV/CA、ML 和 packaging 均未实现。

旧 Stage 4 concentration backend 暂作为隔离的历史 compatibility implementation 保留，以保护既有科研回归；新 Generic Event path 不导入它。PB42 的严格 42-file preset 与 snapshot test同样保留为历史科研回归，但 Generic runtime 不再包含固定 A/B/C comparison helper、42-file alias 或 PB42 lazy import。

## Stage 5.3.1 Generic i-t Event GUI

i-t 页面现已启用“数据与曲线 / 分析设置 / 统计结果 / 结果图表”完整工作流。分析设置包含 i-t 专用 Sample ID/Group/Notes metadata（不使用 Bare/Material）、任意 Event name/time/value/unit/notes 的 Event Timeline、默认 20% 的 segment 尾段比例、signed/magnitude 指标，以及默认关闭的可选 Calibration。Timeline 按时间自动排序，Event ID 在编辑中保持稳定；同一时间不能定义两个 Event。没有任何 effective Event 时直接进入 Continuous mode；一旦定义 Event，则相关 Timeline 必须确认后才能正式分析。

Baseline 明确定义为记录起点至首个 Event；每个 Event 从自身时间延续到下一个 Event，最后一个延续到记录末尾。正式 response、SD、signed ΔI 与 magnitude 全部来自 Stage 5.3 backend 的多点窗口结果。共享 Timeline 可用于 1/N 条不同时长的记录，短记录缺少的后期窗口以 unavailable row 保留，不删除整条记录。

Calibration 不会因 Event 带 numeric value 而自动开启或自动纳入。用户必须显式启用、填写通用 x label/unit，并逐项选择 Events；缺失数值、单位不完全一致或不足两个不同 x 值均由 backend validation 阻止，不进行单位换算。结果区直接展示 backend 的 Event Response、Event Summary、可选 Calibration 和 warnings/QC；图形包括完整 raw curves + Event markers、individual response scatter + group mean ± sample SD，以及通用 OLS calibration。individual response hover 使用正式 Sample ID，不从文件名推断。

每个 Workspace 分别保存 i-t metadata、Event Timeline、settings、result、plot 与 export 状态；i-t 与 LSV workflow 也互相隔离。修改 metadata、Timeline、tail fraction、metric 或 Calibration 会把既有结果标为 stale，重新分析前禁止以新设置导出旧结果。Stage 5.3.1 GUI 暂不暴露 explicit-window editor，但 Stage 5.3 backend 的 explicit `ResponseWindow` 能力继续保留。

## Stage 5.3.1.1 i-t GUI usability and sample Timeline overrides

Event Timeline 行现在支持双击任意 Event/Time/Value/Unit/Notes 列打开整行编辑器，原“编辑”按钮继续保留；Event ID 是稳定内部 identity，不能由普通编辑操作改变。样本信息主标题精简为“① 样本信息”。

i-t Timeline 采用两层且仅两层的继承模型：一个 Workspace-local **Default Timeline**，加上以稳定 canonical `record_key` 关联的 optional per-sample override，不存在 Group-level Timeline。没有 override 的 included record 继承 Default；首次创建 override 时完整复制 Default Events 并保留 event_id/name/value/unit/notes，之后通常只需调整实际 time。override 内容独立于 Default，修改 Default 不覆盖既有 override；恢复默认会删除该 record 的 override。Sample ID 政名不会改变绑定，Include=False 暂时保留 override，删除 record 则清理 orphan。

Default 与每个 override 分别确认。已创建但未确认的 override 不会静默 fallback；正式分析会阻止并指出对应 Sample。GUI orchestration 按 record 选择 confirmed Timeline，然后逐条复用 Stage 5.3 `analyze_it_events()`，最终继续用 backend `summarize_event_responses()` 按 event_id 汇总。某个 override 删除 Event 不会令后续 Event 按行号错位。Calibration selection 仍是 Workspace-level logical event_id 集合；不同 Sample 可拥有不同 Event time，但必须保留被选择 Event 的 compatible value/unit。

所有通过 `plotting.common.new_figure()` 创建的 LSV/i-t 科研图与 GUI raw preview 现在共享同一个 CJK font policy；Windows 优先 Microsoft YaHei/SimHei，再使用跨平台 fallback，不提交字体文件。Calibration 未产生结果时，结果图 selector 只显示 Raw + Events 和 Event Response；只有本次 result 实际包含 calibration 才显示 Calibration。若旧选择已失效会自动回退到 Raw + Events，且 disabled Calibration 不构建或导出 calibration figure/CSV。

## Stage 5.3.1.2 Event display identity and stable footer

Event 主表现在只显示按当前 Timeline 时间顺序在每次 render 时生成的连续 `#`，不再向普通用户展示 `event_17` 一类内部 ID。Display index 不是 Event model、analysis result 或 export 字段；Treeview iid、编辑、删除、Default/override 对齐、Calibration selection、response summary 与 CSV provenance 仍使用真实且不复用的稳定 `event_id`。删除或重新排序 Event 只会改变显示序号，不会重编号 scientific/internal identity。Calibration 列表同样显示易读序号，并通过独立映射保存真正 event_id，不从显示文本反向解析。

i-t 分析设置 footer 已从三个相互竞争横向空间的 `pack` widgets 改为两列 `grid`：左列用两行显示可换行 status/feedback，右列是固定 action area。wraplength 根据 footer 实际宽度和按钮 requested width 调整，因此 stale、validation error、长中文 Sample ID/Timeline 状态不会再把“开始正式 i-t Event 分析”推离可视区域。按钮在普通、stale、validation failure 和 analysis complete 状态保持可见且 enabled，仅在后台 busy 时 disabled。Workspace 自增显示编号语义刻意未改变。

## Stage 5.3.1.3 Event-optional analysis and batch metadata

Generic i-t formal analysis now has two explicit result modes. If every included record's effective Timeline is empty, analysis runs in **Continuous mode** without Timeline confirmation and without inventing an Event. Its backend summary uses each complete record and reports Sample ID, Group, duration, mean/sample SD/min/max current in µA, first/last time, and status. The only result plot is the complete raw i-t series; export contains `continuous_summary.csv` plus the raw figure and deliberately omits Event/response/Calibration CSVs. Calibration is unavailable and its prior state is cleared when the workflow becomes Continuous.

If the Default Timeline or an included sample override contains an Event, the batch enters **Event mode**. Defined but unconfirmed Timelines remain blocking; confirmed Timelines continue through the unchanged Stage 5.3 baseline, tail-fraction, signed ΔI, magnitude and explicit Calibration formulas. Empty effective Timelines in an Event batch may be explicitly confirmed and yield absent responses rather than being silently analyzed as continuous records.

i-t metadata reuses the LSV `MetadataSelectionModel`: normal click, Ctrl-click, Shift range selection, Ctrl+A, drag range selection, Select All and Clear Selection follow the same interaction pattern. Stage 5.3.1.3.1 exposes the common actions directly below the table in LSV-like order: editable Group Combobox + “设置 Group”, “纳入”, “不纳入” and compact “设置备注”. Existing non-empty Group labels populate the Combobox while new labels remain editable; focusing it does not clear the Treeview selection. The former generic batch dialog was removed. Sample ID remains individually editable because assigning one value to several rows would violate uniqueness. Batch edits invalidate metadata confirmation, stale an existing result, and preserve sample Timeline overrides through stable `record_key` identity. Windows checks are listed in `docs/windows_stage53131_checklist.md`.

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
