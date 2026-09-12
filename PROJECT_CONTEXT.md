# Project Context

## Project identity and scope

Electrochemical Workstation Data Analyzer is a desktop-oriented electrochemical data analysis project. Its repository-level identity is generic, while its currently validated native binary parser is deliberately narrower: real-file validation primarily covers CH Instruments CHI760E Linear Sweep Voltammetry (LSV) and Amperometric i-t Curve data. The project must not claim support for every workstation vendor or describe the parser as universal.

The current development state is **Stage 5.3.2**, providing interruption-aware Continuous i-t stability analysis while preserving Event analysis and parser behavior.

## Architecture

- `src/chi_parser/`: strict, validated, technique-specific CHI760E parsing and diagnostics.
- `src/analysis/`: generic metadata, selected-potential LSV analysis/statistics, sign QC, MAD flags, technique routing, and the i-t analysis backend.
- `src/plotting/`: scientific figures built from analysis results.
- `src/export/`: CSV, Excel, figures, and provenance logs.
- `src/chi_gui/`: Tkinter/ttk desktop GUI and independent Workspace state.
- `src/presets/`: optional experiment-specific workflows; PB42 is a preset, not the generic core.
- `tests/`: parser, analysis, export, plotting-adjacent, and GUI regression tests.

The design is **generic-first**: generic core code must not depend on PB42 group names, sample counts, filenames, or fixed comparisons. PB42/H2O2 remains a useful example, validated experimental workflow, and optional preset. Internal package names such as `chi_parser` and `chi_gui` are intentionally retained until any future package migration is designed and tested as a separate stage.

## Scientific invariants

Raw `.bin` files are read-only. The parser is responsible only for reliable decoding, validation, provenance, and immutable numerical arrays; it must not modify scientific data.

The default pipeline performs no smoothing, normalization, baseline correction, or automatic outlier removal. It must not silently add any of these operations. MAD is a **Possible outlier** flag only and never removes an observation automatically.

For LSV selected-potential analysis, the user explicitly supplies the target potential E*. If E* matches an actual sample within the validated tolerance, the actual sample is used. If E* lies between two valid grid points, current is obtained by linear interpolation. Extrapolation is forbidden. The software must not search for the most significant p-value, largest group difference, “best potential,” or any other data-selected target.

Signed current and absolute magnitude are both retained because magnitude can conceal current-direction reversal. Current-sign QC reports positive, negative, and near-zero counts without changing inclusion or values. A comparison is performed only when explicitly defined by the user; Generic Mode does not automatically generate every pairwise comparison.

## Metadata and statistical membership

`Workspace`, `Group`, and `Electrode Type` are distinct concepts:

- A **Workspace** is an independent GUI working container/session. It may contain multiple Groups and is never converted automatically into a statistical Group.
- A **Group** is a user-confirmed experimental condition.
- **Material** and **Bare** are Electrode Type values. A Bare control may share the same Group as Material electrodes under the same experimental condition.

Current Generic LSV formal statistics use only `Material`. `Bare` remains available for raw visualization, metadata/provenance, and control inspection, but it does not enter Material mean, sample SD, SEM, CV, MAD flags, sign-QC Material counts, pairwise Welch/Mann–Whitney tests, overall Welch ANOVA/Kruskal–Wallis tests, Hedges' g, selected-potential Material scatter, or Material mean curves.

Descriptive output currently includes n, mean, median, sample SD, SEM, CV%, minimum, Q1, Q3, and maximum. Explicit comparisons currently provide a Welch independent-samples t-test, Mann–Whitney sensitivity analysis, mean difference `LEFT - RIGHT`, bootstrap confidence intervals, Hedges' g, and Holm correction within a configured Primary family. Bootstrap seeds and resample counts are recorded for reproducibility.

For 3 or more Material Groups, the current selected-potential metric is also analyzed with one-way Welch ANOVA and Kruskal–Wallis sensitivity analysis using every confirmed included Material Group. The two omnibus results are always reported side by side and never gate explicit pairwise comparisons. With fewer than 3 Groups they are not applicable; formal omnibus calculation also requires `n >= 2` in every participating Group. No group-subset selection, classical equal-variance ANOVA, automatic normality-test routing, Tukey, Games–Howell, or Dunn procedure is implemented.

Each included Material sample is currently treated as one statistical input unit. The software does not infer biological versus technical replication, electrode nesting, paired observations, repeated measures, or batch structure. Experiments with those designs require a separately designed paired, repeated-measures, or mixed-effects analysis; none is implemented in Stage 5.2.3.

## Current GUI and backend status

The GUI currently provides multiple independent Workspaces, file/folder import, raw curve preview, per-curve visibility, numeric cursor control, LSV selected-potential readings, editable metadata, configurable Groups, Bare/Material classification, formal Generic LSV analysis, result tables, publication plots, Sample ID hover on selected-potential scatter, and export. Confirmed Material metadata automatically determines 1, 2, 3, or N Groups. Single-group analysis needs no comparison; multi-group analysis accepts any user-declared pairwise comparisons without generating all pairs automatically. Descriptive tables and scientific plots retain every Material Group. Overall multi-group results appear in their own results tab; the existing Left Group / Right Group / Role / Holm Family / Name pairwise editor is intentionally retained unchanged.

The data page owns an independent horizontal pane layout with bounded left/right minimum widths and a remembered sash fraction. Other workflow pages cannot feed their requested Treeview or canvas width back into the data-page split. Long curve filenames use bounded display labels while their full path remains available in details/provenance.

Generic i-t has two explicit formal modes. Continuous mode applies only when every included record's effective Timeline is empty; it needs no Timeline confirmation and invents no Event. Stage 5.3.2 adds shared user-defined absolute analysis/Early/Late windows, Early/Late mean and sample SD, signed and magnitude change, magnitude Retention, raw-current OLS drift, per-record interruption metadata, valid-segment metrics, partial-validity QC and Group descriptive summaries. Blank analysis bounds resolve to each record's actual sampled bounds; uncovered or under-sampled windows are unavailable per record rather than aborting the batch. Event mode applies when any included effective Timeline contains Events. Its existing baseline/reference and response-window formulas, tail-fraction policy, signed delta, magnitude and explicit unit-consistent Calibration remain unchanged. A defined but unconfirmed Timeline blocks Event mode rather than being silently ignored.

Continuous invalid/interruption intervals are formal analysis metadata bound to stable record identity. They never delete or mutate raw samples. An interval divides an analysis range into numbered valid segments. The formal overall OLS drift is unavailable when its range crosses an interruption, while each sufficiently sampled valid segment retains its own mean, sample SD, slope and R². Early/Late windows that overlap invalid time are unavailable; samples are not silently dropped to complete the calculation. Retention across an interruption is allowed only from two otherwise valid windows and is explicitly flagged `interrupted`, so it is interpreted as a before/after response ratio rather than proof of uninterrupted stability. No interruption repair, gap interpolation, smoothing, baseline correction, normalization, detrending, exponential decay, t50/t90, peak, recovery or AUC analysis is performed.

Formal i-t Event times must be user-confirmed. Cursor readings may seed an editable Event draft only through an explicit GUI action; moving the cursor never changes the formal Timeline, invalidates a result, or enters formal statistics automatically. No smoothing, baseline correction, event detection, unit conversion, response-time/t90/peak/recovery/AUC calculation, or single-point formal response is performed. The roadmap may consider those time-series features separately.

## Known follow-up work

The formal Generic i-t GUI now provides Sample ID/Group/Notes metadata, LSV-consistent multi-row selection and atomic Include/Group/Notes batch editing, an optional arbitrary Event Timeline, cursor-assisted draft creation, result tables/plots, and mode-aware export. The i-t table exposes an editable Group Combobox plus direct Set Group / Include / Exclude / Set Notes actions; existing Group labels refresh from current metadata, and the obsolete generic batch dialog is not retained as a second path. Sample ID stays individually editable because it must remain unique. Batch metadata edits preserve Timeline overrides by stable record key, invalidate metadata confirmation, and stale completed results. Calibration is optional in Event mode and unavailable in Continuous mode; numeric Events are never selected automatically. The GUI intentionally exposes only the default tail-fraction policy for Event mode while the backend retains explicit-window support. It does not expose a fixed Concentration/µM schema or Bare/Material roles.

i-t Timeline inheritance deliberately has only two levels: one Workspace-local Default Timeline plus optional per-sample overrides. There is no Group-level Timeline. Overrides are keyed by stable canonical record identity rather than editable Sample ID, are initially copied from Default with logical event_id values preserved, and then evolve independently. Default and every override have separate confirmation states; an existing unconfirmed override blocks formal analysis instead of silently falling back. Include=False preserves its override, record removal cleans the orphan, and Sample ID changes do not detach it. Formal orchestration chooses the confirmed Timeline per record and aligns responses/summaries/calibration by event_id, never by row index.

All scientific figures share one CJK-capable Matplotlib font policy. Windows prefers Microsoft YaHei/SimHei without bundling font files. The result-plot selector exposes Calibration only when the current completed result actually contains calibration output and safely falls back to Raw + Events if a prior selection becomes unavailable.

An Event display index is not its `event_id`. The GUI derives `1..N` from the current time-sorted Timeline only for presentation. Stable `event_id` remains the immutable scientific/internal identity used for Treeview iid, Default/override alignment, Calibration selections, response summaries, stale signatures, and export provenance; deleted IDs are not reused and display reordering never renumbers them. Workspace display numbering remains a separate UI convention and is unchanged.

The i-t settings footer reserves an independent action column for the run button. Status and feedback occupy a bounded, wrapping text column, so long stale or validation messages cannot displace the action. The run action stays available for correction/reanalysis and is disabled only while background work is busy.

The existing `ComparisonDefinition` remains the explicit pairwise contract between any two Groups. Omnibus results are stored separately and must not be inserted into pairwise rows. Do not add Games–Howell, Tukey, Dunn, paired/repeated-measures, or mixed-effects tests without a separate scientific/statistical design discussion.

## Near-term roadmap and change discipline

PB42 remains only in `presets.pb42` and historical fixtures/tests. The obsolete `infer_experiment_manifest` alias, package-level lazy PB42 exports, and fixed A/B/C Generic comparison helper were removed in Stage 5.3. Generic runtime does not import PB42. Later CV/CA support requires dedicated parsers and technique-specific scientific semantics. Machine learning, broad vendor claims, and large package renames remain outside scope.

Any future change must preserve raw-data immutability, provenance, user-confirmed metadata, explicit target/comparison definitions, non-destructive QC, signed values, and separation of parser, analysis, plotting, export, GUI, and optional presets.
