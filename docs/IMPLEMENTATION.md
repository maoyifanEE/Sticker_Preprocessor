# Implementation Notes

## Architecture

The project uses a `src` package layout. UI, image I/O, analysis, checkerboard logic, AI integration, export, runtime paths, and logging are separate modules.

## Processing Decision Tree

`AUTO` first checks meaningful real transparency. If present, it uses alpha cleanup. Otherwise it runs conservative checkerboard detection. If confidence is high, checkerboard removal is used. If not, it falls back to AI mode.

Manual alpha cleanup rejects opaque images. Manual checkerboard mode refuses low-confidence detections instead of silently falling back.

## Alpha Semantics

The loader converts working images to RGBA but records the original decoded mode. A source file having an Alpha channel is distinct from containing meaningful non-opaque pixels.

Meaningful transparency counts pixels with Alpha `< 250` and requires at least `max(64, 0.01% of pixels)`.

## Checkerboard Detection

The detector samples border strips, quantizes RGB values, finds two dominant light neutral colors, checks coverage, estimates tile size from alternating runs, then validates parity patterns with multiple phases. Automatic removal requires confidence at least `0.85`.

## Border Connectivity Safety

Removal builds a candidate mask from distance to the expected local checker color. Only candidate pixels connected to the outer border are made transparent, so enclosed similar colored subject regions are preserved.

## rembg Lazy Loading

Only `rembg_adapter.py` imports `rembg`, and it does so lazily. Before import, `U2NET_HOME` is set to `.runtime\models\rembg` unless already supplied in the process environment.

Sessions are cached by allowlisted model name and protected by a lock.

## Threading Model

The Tkinter UI uses `ThreadPoolExecutor(max_workers=1)`. Worker threads process images and return structured results. The Tk main thread polls futures with `after(...)`, updates widgets, creates `PhotoImage` objects, and shows dialogs.

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
