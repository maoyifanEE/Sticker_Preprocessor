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

## Save-As And Output Folder

Default export writes to `output` with collision numbering. Save-as uses a native save dialog, PNG-only extension, sanitized default filename, overwrite confirmation, and the same atomic encode/verify path in the worker. Opening the output folder uses `os.startfile(output_dir())` without shelling untrusted text.

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

Exports go to `output`.

## Error Handling

Expected failures use typed exceptions with Chinese UI messages. Unexpected failures are logged with tracebacks and shown as concise UI errors.

## Future Extension Points

- Batch processing can be added above `pipeline.py`.
- Additional AI models must remain allowlisted in `rembg_adapter.py`.
- Manual masking should be a separate UI layer and must not mutate source files.
