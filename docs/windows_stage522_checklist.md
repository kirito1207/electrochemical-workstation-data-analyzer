# Stage 5.2.2 Windows GUI 人工验收清单

## Data page layout

1. 在“数据与曲线”记录正常左右比例；完成正式分析、查看“统计结果”和“结果图表”后切回，确认左侧 raw preview 不变窄、右侧不异常放大。
2. 最大化窗口后完成分析并切回数据页，再恢复窗口；确认 sash 保持合理比例，左右 pane 都不低于可用最小宽度。
3. 手动缩放窗口并来回切换四个 workflow tabs；确认结果表和结果 Figure 的宽度不改变数据页分栏。
4. 拖动数据页 sash 到合理位置，切换 tab 后返回；确认用户比例被恢复，而不是跳到极端值。
5. 导入含超长中文/英文文件名的文件；确认右栏不无限扩张，曲线列表使用有界名称，实验参数/详情仍能查看完整路径。
6. 展开/折叠日志、切换 Workspace、移除和重新导入文件；确认 data-page layout 仍稳定。

## Multi-group workflow

1. 仅设置 1 个 Material Group、不添加 comparison，确认正式分析、描述统计、MAD、sign QC 和全部适用图可用，并显示单组提示。
2. 分别使用 2、3、4 个 Material Groups，确认 Group 数由 confirmed metadata 自动识别，描述表与图不遗漏任何组。
3. 使用较长且完全自定义的 Group 名称，确认 selected magnitude/signed 与 CV% 标签保持可读。
4. 四组时只添加 A vs B 与 A vs D，确认只运行这两条 comparison；随后添加全部六条 pairwise，确认全部保留。
5. 尝试选择相同 Left/Right，确认 inline 显示“Left Group 与 Right Group 不能相同。”且不添加 comparison。
6. 将多个 Primary comparisons 放入同一 Holm Family，确认 Holm 仍只校正该 family 的 Welch p。
7. 检查 Raw curves 与 Mean ± SD 的 `ALL` 及每个 Group filter；Raw `ALL` 应包含全部 Material 与 Bare，Bare 保持黑色虚线。
8. 检查 mean overlay、selected magnitude、selected signed 与 CV% 均覆盖全部 Material Groups。
9. 在每组 hover first/middle/last/edge 和 S11-like point，确认显示 confirmed Sample ID，magnitude/signed 值不串组。
10. Workspace 1 使用 A/B/C，Workspace 2 使用 X/Y；切换后核对 metadata、comparison candidates/table、result、plot Group、target、metric、validation 与 export state 均不串。

Stage 5.2.2 不验收 i-t formal GUI，也不包含 ANOVA、Welch ANOVA、Kruskal–Wallis、Tukey、Games–Howell 或 Dunn。
