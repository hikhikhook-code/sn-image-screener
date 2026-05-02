# Design notes — SN IMAGE SCREENER

## Goals

* A clean, modern, brutalism-inspired desktop app for **local** image quality screening.
* Beginners should reach a useful result in three steps: **add → preset → scan**.
* Power users get full control of every threshold via the collapsed **Advanced** drawer.
* The app must be readable on a 1366×768 laptop screen.

## Layout

```
┌──────────────────────────────── COMMAND BAR ─────────────────────────────────┐
│  SN IMAGE SCREENER                  [Add Folder][Add Files][Start][Stop]…    │
│  LOCAL · IMAGE · QUALITY · SCREENING                              [● READY]  │
├────────────┬─────────────────────────────────────────────┬───────────────────┤
│  CONTROL   │  SUMMARY  +  PROGRESS                       │   INSPECTOR       │
│  PANEL     │  ─────────────────────────────────────────  │   ─────────────── │
│            │  RESULTS TABLE                              │   Large preview   │
│  Source    │  Thumb · File · Status · Score · Issues …   │                   │
│  Preset    │                                             │   Metric blocks   │
│  Quality   │                                             │   Issue chips     │
│  Output    │                                             │                   │
│  Advanced  ├─────────────────────────────────────────────┤                   │
│            │  ACTIVITY LOG (internal scroll)             │                   │
└────────────┴─────────────────────────────────────────────┴───────────────────┘
```

The horizontal split is resizable; the vertical split between table and
log is also resizable. The control panel scrolls independently, and the
inspector clamps its preview pixmap on resize.

## Brutalist style

| Element     | Choice                                 |
| ----------- | -------------------------------------- |
| Base        | `#F4F1EA` (warm cream)                 |
| Surface     | `#FFFFFF`                              |
| Surface alt | `#EAE6DC`                              |
| Ink         | `#111111` (text + 2px borders)         |
| Accents     | Orange `#FF4D2E` · Lime `#D6EE2C` · Cobalt `#1F36C7` · Yellow `#FFC700` |
| Status      | PASS lime · REVIEW amber · REJECT red · ERROR black/yellow |
| Borders     | 2 px, hard, ink-coloured               |
| Corners     | square (no rounding)                   |
| Type        | Inter / Segoe UI for prose, monospace for numbers |

Accent blocks are used **sparingly**, on action buttons and status tags
only. The rest of the UI keeps light surfaces with hard charcoal frames.

## Detection pipeline

```
read bytes  →  cv2.imdecode  →  grayscale  →  metric block:
                                            ├─ Laplacian variance        (blur)
                                            ├─ stddev(absdiff(gray, blur)) (noise)
                                            ├─ histogram + percentiles   (exposure / dynamic range)
                                            └─ 8×8 boundary diff         (jpeg artifact, JPG only)
                                                       │
                                                       ▼
                                                classify(metrics, rules)
                                                       │
                                                       ▼
                                       Verdict( status, 0..100 score, issues[] )
```

* Each metric is mapped to a 0..100 sub-score via a piecewise-linear
  ramp around the `review` and `reject` thresholds of the active preset.
* The overall **quality score** is a weighted mean (blur 0.35,
  noise 0.25, exposure 0.20, artifact 0.20) with hard caps applied:
  REJECT can never score above 49, REVIEW above 79, and a file that
  fails the size or resolution gates is capped at 35.
* Status priority: any reject-severity issue → **REJECT**; otherwise any
  review-severity issue → **REVIEW**; otherwise → **PASS**.

## Threading

The scanning loop runs in a `ScanWorker` QObject moved onto a dedicated
`QThread`. The UI receives `item_done(ScanItem)` and `progress(i, n)`
signals; the worker exposes a cooperative `stop()` that the **Stop**
button triggers.

## File safety

* `compute_metrics` reads the file via `open(path, "rb")` + `cv2.imdecode`.
  No write paths exist anywhere in `core/detection.py`.
* `screen_one` only constructs a read-only `ScanItem`.
* `exporter.copy_by_status` only ever writes **into** the user-selected
  output folder, using `shutil.copy2`. It never opens the source file
  for write.
* The UI never offers a destructive operation on the source file.
