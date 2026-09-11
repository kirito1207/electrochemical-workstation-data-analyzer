# Stage 5.2.3 Windows manual acceptance checklist

Use the existing PowerShell 7 environment and validated local data. Do not modify source `.bin` files.

- 1 Material Group: formal analysis succeeds; “整体多组比较” explicitly says not applicable.
- 2 Material Groups: overall tests say `>=3 Groups` is required; explicit pairwise results still work.
- 3 Material Groups: Welch ANOVA and Kruskal–Wallis rows show statistic, df and p-value.
- 4/N Material Groups: both omnibus tests use all included Material Groups with no truncation.
- Define only `A vs B` and `A vs C`: only those pairwise results appear while omnibus uses every Group.
- Switch magnitude/signed and rerun: omnibus metadata and values follow the selected metric.
- Give one participating Group only one Material sample: both tests show unavailable with the Group and n.
- Put Bare and Material in the same Group: Bare remains visible in raw curves but does not change omnibus n.
- Edit Group/metric/target after analysis: result becomes stale and export remains disabled until rerun.
- Workspace 1 with 4 Groups and Workspace 2 with 2 Groups: overall results never cross Workspaces.
- Export: verify `omnibus_statistics.csv`, Excel `Omnibus statistics`, and JSON provenance.
- Switch 统计结果 → 结果图表 → 数据与曲线, maximize/restore, and switch Workspaces: data-page pane widths remain stable.
- Hover first/middle/last selected-potential Material points in every Group: confirmed Sample ID and correct signed/magnitude value remain mapped.

No omnibus-specific scientific plot or p-value annotation is expected in Stage 5.2.3.
