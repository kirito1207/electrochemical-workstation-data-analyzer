# Stage 5.2 Windows GUI 人工验收清单

1. 使用 `python -m chi_gui` 启动，确认 LSV 页存在四个 workflow tabs。
2. 导入中文/空格路径下的多份 LSV 与一份 i-t；确认 LSV 正式设置表只列 LSV，i-t 仍仅提供预览。
3. 检查 raw preview、visibility、selected highlight、数值 cursor 和左右键仍正常且界面无卡死。
4. 修改 Sample ID、中文/英文 Group、Material/Bare、Notes 与 Include；确认 preview visibility 与 Include 相互独立。
5. 未点击“确认样本信息”时尝试分析，确认只显示中文校验提示且不启动任务。
6. 确认 manifest，设置一个采样点电位及一个需要插值的电位；确认分析均可完成。
7. 点击“使用当前游标电位”，确认只有显式点击才改变 draft analysis potential。
8. 添加 Primary comparison 和 Holm family，再添加无 family 的 Exploratory comparison；检查结果表。
9. 检查 descriptive、Welch、Mann–Whitney、Holm p、Hedges' g/CI、sign QC、MAD 和 All data included 提示。
10. 修改分析电位后确认结果显示 stale，且重新分析前不能导出。
11. 在结果图页逐一切换 raw、mean ± SD、overlay、signed/magnitude scatter 和 CV%，确认一次仅显示一张图。
12. 导出两次到同一父目录，确认生成两个不同时间戳/后缀目录，且包含 Excel、CSV、PNG、SVG、PDF、JSON。
13. 新建并切换 Workspace，确认 metadata、settings、comparisons、result 与图表彼此独立。
14. 确认关闭/清空 Workspace 不删除任何原始 `.bin`，旧科研 `results/` 不被覆盖。
