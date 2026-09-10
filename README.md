# chi760e-h2o2-analyzer

当前开发状态：**Stage 3（parser v0.1 + 可配置 LSV 批量统计分析）**。

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

`run_lsv_analysis()` 对已确认的 42 文件实验设计执行完整且可追踪的分析。分析电位不是固定值；默认 `0.000 V`，也可由调用方设置为扫描范围内的任意电位。精确采样点直接读取，非采样电位使用左右相邻真实点线性插值，禁止外推。

```python
from analysis import AnalysisSettings, run_lsv_analysis

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
