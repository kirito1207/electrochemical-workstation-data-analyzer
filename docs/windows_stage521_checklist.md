# Stage 5.2.1 Windows GUI 人工验收清单

1. 导入一个含 14 个 LSV 的目录，点击“全选”，批量设置 Group，再单独把裸电极设为 Bare；确认 Confirm 成功信息直接显示在设置页。
2. 从 3 个不同目录导入共 42 个 LSV，分别向下和向上拖选连续 14 行并批量设置 Group；确认跨目录不会阻止 manifest confirmation。
3. 保留某些 included 行的 Group/Sample ID 为空，点击 Confirm；确认设置页汇总缺失数量并显示少量 Sample ID/文件名预览。
4. 在同一 Group 内制造重复 Sample ID，确认显示“Group … 中 Sample ID … 重复”；相同 Sample ID 位于不同 Group 时应允许。
5. Workspace 1 填写但不添加 comparison 草稿，切换到 Workspace 2；确认 Left/Right/Name 清空，Role=`Primary`、Holm Family=`primary`。
6. Workspace 1 添加正式 comparison，切到空的 Workspace 2 再切回；确认正式 comparison 表恢复且未串到 Workspace 2。
7. 检查 Ctrl+单击、Shift+单击、Ctrl+A、全选、取消选择和上下拖选；拖选后不应弹出 metadata 编辑框，普通双击仍可编辑。
8. 单 Group、至少 2–3 个 Material、无 comparison 运行正式分析；确认描述统计、QC 和图表可用。
9. MAD 无 flag 时确认显示“未发现 MAD Possible outlier”，并明确所有 Material 仍纳入；有 flag 时确认仅标记、不删除。
10. 检查 sign QC：方向一致时显示成功提示，mixed signs 时显示 magnitude 解释警告但不阻止分析。
11. 在“指定电位 |I|”与“指定电位 Signed I”图上逐点 hover，核对确认后的 Sample ID 和 signed/magnitude 电流；移开后 annotation 自动隐藏。
12. 确认 Bare、mean marker、SD errorbar 不出现 Sample ID hover，13–42 点移动流畅且不触发重复分析/重绘。
13. 导出 PNG/SVG/PDF，确认静态图没有永久 Sample ID 标签，结果数值和旧版本一致。
14. 修改 metadata、Include、分析电位、metric 或 comparison，确认旧结果标为过期且禁止按当前设置导出。
