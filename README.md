# chi760e-h2o2-analyzer

当前开发状态：**parser v0.1**。

本阶段提供严格校验的 CH Instruments CHI760E 二进制解析基础设施。parser 只读取原始数据，不进行平滑、基线校正、归一化、统计分析或绘图。

## 当前支持范围

- Linear Sweep Voltammetry（`LSV`）
- Amperometric i-t Curve（`i-t`）

当前已使用 1 个真实 LSV 文件和 1 个真实 i-t 文件进行 regression validation。

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

parser、analysis、plotting 和 GUI 将保持职责分离。

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

