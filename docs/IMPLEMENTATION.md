# Implementation Notes

## Architecture

The project uses a `src` package layout. UI, image I/O, analysis, checkerboard logic, AI integration, export, runtime paths, and logging are separate modules.

## Processing Decision Tree

`AUTO` first checks meaningful real transparency. If present, it uses alpha cleanup. Otherwise it runs conservative checkerboard detection. If confidence is high, checkerboard removal is used. If not, it falls back to AI mode.

Manual alpha cleanup rejects opaque images. Manual checkerboard mode refuses low-confidence detections instead of silently falling back.

## Preview Backgrounds

Preview compositing supports light, dark, and web-gradient backgrounds. The web option is a real light blue to cream gradient generated with Pillow and NumPy. Checkerboard preview is intentionally not offered by default because it would recreate the same ambiguity the application is designed to remove.

Preview compositing never modifies the real output image. Source and result previews use the same selected background.

## Alpha Semantics

The loader converts working images to RGBA but records the original decoded mode. A source file having an Alpha channel is distinct from containing meaningful non-opaque pixels.

Meaningful transparency counts pixels with Alpha `< 250` and requires at least `max(64, 0.01% of pixels)`.

Very low Alpha residue can form an almost invisible full-frame rectangle. CSS shadows and light page backgrounds can amplify that residue into a visible box, so the pipeline records detailed Alpha diagnostics and applies border-connected haze cleanup.

## Alpha Diagnostics And Quality Gate

`diagnostics.py` computes Alpha histograms, threshold bounding boxes, outer-edge metrics, corner metrics, conservative haze reason codes, and final quality verdicts. Reports are written to `.runtime\reports\<run-id>.json` atomically for successes and practical failures.

The quality gate checks RGBA mode, real transparency, non-empty foreground, transparent border padding, residual rectangular haze, dimensions, and RGB cleanup where Alpha is zero. Known rectangular haze fails instead of exporting silently.

Route-specific haze thresholds are named constants:

- `ALPHA_SOURCE_HAZE_CUTOFF = 8`
- `GENERATED_RESULT_HAZE_CUTOFF = 32`

The cleanup flood-fills only low-Alpha candidate pixels connected to the image border. Interior low-Alpha details and near-opaque Alpha 251-254 subject pixels are preserved.

## Checkerboard Detection

The detector samples border strips, quantizes RGB values, finds two dominant light neutral colors, checks coverage, estimates tile size from alternating runs, then derives candidate x/y phase offsets from scan-line transitions. Candidate phases are scored on sparse sample points, so arbitrary crop offsets can be recovered without scanning every pixel for every possible phase.

Automatic removal requires confidence at least `0.85`.

## Border Connectivity Safety

Removal builds a candidate mask from distance to the expected local checker color. Only candidate pixels connected to the outer border are made transparent, so enclosed similar colored subject regions are preserved.

## rembg Lazy Loading

Only `rembg_adapter.py` imports `rembg`, and it does so lazily. Before import, `U2NET_HOME` is set to `.runtime\models\rembg` unless already supplied in the process environment.

Sessions are cached by allowlisted model name and protected by a lock. Third-party exception details are logged with traceback but normal UI errors use stable Chinese messages.

## Threading Model

The Tkinter UI uses `ThreadPoolExecutor(max_workers=1)` for load, analysis, processing, AI work, export encoding, and export verification. Worker threads return typed payloads. The Tk main thread polls futures with `after(...)`, updates widgets, creates `PhotoImage` objects, and shows dialogs.

The UI tracks an operation generation so stale completions cannot replace newer state.

The UI exposes diagnostic controls for exporting a review bundle and opening the log folder. The result panel displays run ID, selected route, quality result, removed haze pixels, final border Alpha count, key Alpha bounding boxes, and warnings.

## Save-As And Output Folder

Default export writes to `output` with collision numbering. Save-as uses a native save dialog, PNG-only extension, sanitized default filename, overwrite confirmation, and the same atomic encode/verify path in the worker. Opening the output folder uses `os.startfile(output_dir())` without shelling untrusted text.

## Review Bundles And QA Batch

`review_bundle.py` creates local ZIP files under `.runtime\review-bundles`. A single-image bundle contains `manifest.json`, `report.json`, current-run log lines, the selected input image, optional processed output PNG, and light/dark/web previews.

The bundle intentionally contains selected images and is created only after explicit user action. Nothing is uploaded automatically.

`qa_batch.py` powers:

```powershell
python -m sticker_preprocessor --qa-batch input
```

It processes supported images in sorted order, continues after per-image failures, writes reports and previews under `.runtime\qa-runs`, and creates one final local review ZIP.

## Personal_Web Bridge Contract

`bridge_contract.py`, `bridge_cli.py`, `bridge_events.py`, and
`bridge_manifest.py` implement the Personal_Web handoff provider contract.

The bridge is intentionally separate from the Tkinter UI. It supports two
commands:

* `--bridge-capabilities`
* `--bridge-process-request <request.json>`

Capabilities output is exactly one JSON object on stdout.

Request processing validates:

* contract and schema versions
* exact top-level request keys
* bridge run ID format
* regular input file path
* byte count and SHA-256 hash
* supported MIME type
* allowlisted processing mode and AI model
* bounded padding and Alpha crop threshold values

Processing stdout from the normal pipeline is redirected so the bridge response
remains machine-readable. Each run writes JSONL events, a sanitized request,
`processed.png`, `result.json`, and the normal processing report when available.

The bridge has stable failure responses and exit codes. It prunes bridge runs
older than seven days. It does not import Personal_Web code, call Personal_Web
APIs, upload media, write a database, or decide whether an output should be
published.

## Close During Processing

If a task is running, closing asks for confirmation. On confirmation the window disables controls, waits for the current worker operation to finish safely, then shuts down the executor and destroys the Tk window. Running file writes or model initialization are not forcibly killed.

## Export Guarantees

Export writes a temporary PNG, verifies it reopens as RGBA PNG with real transparency, atomically replaces the final file, then verifies again. Original input files are never overwritten.

## Runtime Directory Rules

All runtime data stays under `.runtime`:

- `.runtime\logs`
- `.runtime\models\rembg`
- `.runtime\temp`
- `.runtime\test-temp`
- `.runtime\reports`
- `.runtime\qa-runs`
- `.runtime\review-bundles`

Exports go to `output`.

## Error Handling

Expected failures use typed exceptions with Chinese UI messages. Unexpected failures are logged with tracebacks and shown as concise UI errors.

## Future Extension Points

- Batch processing can be added above `pipeline.py`.
- Additional AI models must remain allowlisted in `rembg_adapter.py`.
- Manual masking should be a separate UI layer and must not mutate source files.
