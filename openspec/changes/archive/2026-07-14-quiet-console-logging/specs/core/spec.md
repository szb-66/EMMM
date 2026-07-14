## ADDED Requirements

### Requirement: Console handler emits INFO and above

The console (stdout) handler SHALL emit only records at `INFO` level and above. The logger itself SHALL remain at `DEBUG` so that the file handler still receives `DEBUG` records. `DEBUG` records SHALL NOT appear on stdout.

#### Scenario: DEBUG call does not reach console
- **WHEN** any caller invokes `logger.debug(...)` during a normal run
- **THEN** the message is written to the rotating log file only, and is not written to stdout

#### Scenario: INFO call reaches console and file
- **WHEN** any caller invokes `logger.info(...)`
- **THEN** the message appears on stdout (colored) AND in the rotating log file

### Requirement: Console line uses compact location format

The console formatter SHALL emit the call site as `<logger name>:<function>:<line>` only. It SHALL NOT prepend the verbose `File "<absolute path>", line <n> |` prefix. The file formatter is unchanged and retains full path information.

#### Scenario: Console line shape
- **WHEN** any record at `INFO` or above is formatted for the console handler
- **THEN** the location segment is `<name>:<funcName>:<lineno>` and contains no `File "` substring

### Requirement: File handler retains full DEBUG fidelity

The rotating file handler SHALL remain at `DEBUG`, shall write every record the logger processes, and shall keep its existing field set (`asctime`, `levelname`, `name:funcName:lineno`, `message`). The change to console level/format SHALL NOT alter file output.

#### Scenario: DEBUG written to file after console quieting
- **WHEN** a `logger.debug(...)` call is made
- **THEN** the record is present in the current `LOG_EMMM_*.log` file with full fields

### Requirement: LoggerUtils spec reflects stdlib logging

The documented `LoggerUtils` capability SHALL describe the stdlib `logging` configuration (console + `RotatingFileHandler`), not `loguru`.

#### Scenario: Spec doc string accuracy
- **WHEN** a reader checks the `LoggerUtils` section of the core spec
- **THEN** it references stdlib `logging` and `RotatingFileHandler`, with no mention of `loguru`
