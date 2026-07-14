## 1. Console handler level

- [x] 1.1 In `app/utils/logger_utils.py` `setup_logger`, set `console_handler.setLevel(logging.INFO)` (was `logging.DEBUG`).
- [x] 1.2 Confirm the logger itself (`logger.setLevel`) stays at `logging.DEBUG` so the file handler still receives DEBUG records.

## 2. Console formatter compact location

- [x] 2.1 In `ColoredFormatter.format`, replace the `clickable_location_str` / `colored_location` assignment so only the compact `f"{LogColors.CYAN}{location}{LogColors.RESET}"` variant (`name:func:line`) is used; remove the `File "...", line N` prefix.
- [x] 2.2 Verify no other code path reads `clickable_location_str`.

## 3. Spec doc correction

- [x] 3.1 Update `openspec/specs/core.md` `LoggerUtils` section: change "Configures `loguru` with console + file handlers" to describe stdlib `logging` + console (INFO) + `RotatingFileHandler` (DEBUG).

## 4. Verification

- [x] 4.1 Run app; confirm a known `logger.debug` call (e.g. `FlowLayout.takeAt() monkey-patched...` at `main.py:112`) does NOT appear on stdout but DOES appear in the newest `logs/LOG_EMMM_*.log`.
- [x] 4.2 Confirm a known `logger.info` call (e.g. `main.py:207` "Application starting...") still appears on stdout (compact `name:func:line`, no `File "` prefix) AND in the log file.
