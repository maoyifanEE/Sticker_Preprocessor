# Sticker Preprocessor Handoff Contract v1

Contract version: `personal-web-sticker-handoff-v1`

Personal_Web owns this contract and is the client. Sticker_Preprocessor is an
external provider. The only runtime integration surface is:

```text
versioned JSON request
-> short-lived external process
-> versioned JSON response plus result package
```

Sticker_Preprocessor never calls Personal_Web APIs, never uploads media, never
writes PostgreSQL, and never modifies Journey state. Personal_Web validates the
provider result and decides whether a user-accepted PNG is uploaded and added to
an unsaved Journey draft.

## Commands

```text
python -m sticker_preprocessor --bridge-capabilities
python -m sticker_preprocessor --bridge-process-request <request-json-path>
```

Capabilities must write exactly one compact JSON object to stdout and must not
download models or process images.

Process response must write exactly one compact JSON object to stdout. Logs and
human diagnostics belong on stderr or local log files.

## Exit Codes

* `0`: success
* `2`: invalid request
* `3`: AI component unavailable
* `4`: processing or quality failure
* `5`: unexpected internal failure
* `6`: unsupported contract

## Runtime Artifacts

Sticker_Preprocessor writes local ignored bridge artifacts under:

```text
.runtime/bridge-runs/<toolRunId>/
  sanitized-request.json
  events.jsonl
  handoff/result.json
  handoff/processed.png
  handoff/report.json
```

All paths inside result manifests are relative to the Sticker_Preprocessor root.
Absolute paths, environment values, request cookies, database URLs, and image
bytes must not be logged.
