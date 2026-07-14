## Why

Terminal output during startup and normal use is noisy: the console handler runs at `DEBUG` and each line carries a full `File "...", line N` path. The file handler already records the same full-fidelity stream, so the console duplicates it while burying genuinely useful warnings. Users (and developers watching the terminal) lose signal in the noise.

## What Changes

- Console handler level raised from `DEBUG` to `INFO`; `DEBUG` messages go to file only.
- Console format shortened: drop the verbose `File "...", line N | ` prefix, emit the compact `name:func:line` location instead (the variant already present but commented out in `ColoredFormatter`).
- File handler unchanged: still `DEBUG`, full fields, rotating, for post-mortem debugging.
- `LoggerUtils` spec entry corrected to reflect stdlib `logging` (not `loguru`) and to record the new console/file level split.

## Capabilities

### New Capabilities

<!-- None — no new capability introduced. -->

### Modified Capabilities

- `core`: `LoggerUtils` requirements updated — console handler emits `INFO` and above (was `DEBUG`); console line format uses compact `name:func:line` location (was full `File "..." line` path); file handler retains `DEBUG` with full fields. Doc string corrected from `loguru` to stdlib `logging`.

## Impact

- Code: `app/utils/logger_utils.py` only — `ColoredFormatter.format` and `console_handler.setLevel`.
- Spec: `openspec/specs/core.md` `LoggerUtils` section.
- No API/dependency changes; no behavior change for file logs or for any caller of `logger.*`.
- Risk: developers relying on stdout `DEBUG` visibility must now tail the log file. Acceptable trade-off; DEBUG stays on disk.
