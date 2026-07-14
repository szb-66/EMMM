## Context

`app/utils/logger_utils.py` configures a single `EMMM_App` logger with two handlers: a colored `StreamHandler(sys.stdout)` and a `RotatingFileHandler`. Both currently run at `DEBUG`, so every `logger.debug(...)` call across services/views prints to the terminal in addition to being written to the rotating log file. The console formatter (`ColoredFormatter.format`) also prepends each line with `File "<pathname>", line N | name:func` — a wide, redundant prefix that doubles line length. Net effect: the terminal is flooded during startup (`main.py` emits ~6 info lines plus per-service first-use info) and during normal use (drag-drop, reconciliation, thumbnail generation, toggle all emit info). The file handler already preserves the full-fidelity stream for post-mortem.

## Goals / Non-Goals

**Goals:**
- Reduce terminal noise so warnings/errors remain visible during interactive use.
- Keep full `DEBUG` fidelity on disk for debugging.
- Shrink each console line so more fit on screen.

**Non-Goals:**
- Changing what gets written to the file handler.
- Changing log call sites (no rewrite of `logger.debug` → `logger.info` across services).
- Adding a runtime log-level toggle / config knob. YAGNI; level is fixed in code. If a developer needs DEBUG on console, they edit one constant or tail the file.
- Switching to `loguru` or any new dependency.
- Hiding the console window for frozen builds (separate concern; no `.spec` exists yet).

## Decisions

**D1. Console handler level → `INFO`.**
`console_handler.setLevel(logging.INFO)`. The logger itself stays at `DEBUG` so the file handler (still `DEBUG`) receives everything; the console simply filters. Chosen over `WARNING` because startup/operation `info` lines ("Application starting", "Entering event loop", reconciliation summary) are still useful interactive feedback — `WARNING` would hide too much. Chosen over a per-module `DEBUG` whitelist because that's complexity for a problem we don't yet have.

**D2. Console format: compact `name:func:line` location.**
In `ColoredFormatter.format`, drop the `clickable_location_str` (`File "...", line N | name:func`) branch and use the already-present `location = f"{name}:{funcName}:{lineno}"` variant (currently commented out at `logger_utils.py:58-59`). The file formatter is untouched. Rationale: the `File "..."` form's only value is IDE click-to-jump, which is not how a running terminal is consumed; `name:func:line` is enough to locate the call and is ~40 chars shorter.

**D3. No frozen-build branching.**
`sys.frozen` gating of the console handler is deferred until a PyInstaller `.spec` exists. Adding it now is speculative (rung 1 of the ladder — does it need to exist yet? No).

## Risks / Trade-offs

- [Developers lose stdout `DEBUG` visibility] → Mitigation: file handler still records `DEBUG`; `tail -f logs/LOG_EMMM_*.log` recovers it. One constant edit re-enables console DEBUG if needed.
- [Shorter console location loses click-to-jump in some terminals] → Mitigation: file line keeps full `pathname`; acceptable since terminal is not the primary debug surface.
- [Spec `core.md` says "Configures `loguru`"] → Corrected in this change's delta to stdlib `logging`; no code impact, just doc drift fix.
