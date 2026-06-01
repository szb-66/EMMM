from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from app.utils.logger_utils import logger


class _DirectoryEventHandler(FileSystemEventHandler):
    def __init__(self, owner: "FileWatcherService", key: str):
        super().__init__()
        self._owner = owner
        self._key = key

    def on_any_event(self, event: FileSystemEvent):
        # Ignore noisy events that carry no semantic meaning for refresh
        if event.event_type in {"opened", "closed"}:
            return
        # Ignore directory-creation events (the new directory's contents will
        # trigger file-level events if they matter; a bare mkdir does not change
        # the mod list).
        if event.event_type == "created" and event.is_directory:
            return
        # Ignore directory-modified events (mtime changes on the dir inode —
        # not useful for the mod grid).
        if event.event_type == "modified" and event.is_directory:
            return

        # Filter out paths matching per-key ignore patterns (e.g. internal
        # metadata writes like info.json / properties.json).
        if self._owner._should_ignore(self._key, event.src_path):
            return

        if self._owner.is_suppressed(self._key):
            return

        self._owner.notify_changed(self._key, event.src_path)


class FileWatcherService(QObject):
    """Watchdog wrapper that forwards directory changes through Qt signals.

    Supports recursive watches so nested file/deletion events are detected.
    During suppression windows (internal file operations), events are silently
    dropped.  Callers are responsible for updating the UI directly (the VM
    already patches items in-place before the suppression window expires).
    """

    directory_changed = pyqtSignal(str, object)

    def __init__(self):
        super().__init__()
        self._observer = Observer()
        self._observer.start()
        self._watches = {}
        self._paths = {}
        self._suppression_tokens = {}
        self._ignore_patterns: dict[str, list[str]] = {}

    def watch_directory(self, key: str, path: Path | None):
        normalized_path = path.resolve() if path and path.is_dir() else None

        if self._paths.get(key) == normalized_path:
            return

        self.clear_watch(key)

        if not normalized_path:
            return

        try:
            handler = _DirectoryEventHandler(self, key)
            watch = self._observer.schedule(
                handler, str(normalized_path), recursive=True
            )
            self._watches[key] = watch
            self._paths[key] = normalized_path
            logger.info(f"Watching directory for {key}: {normalized_path}")
        except Exception as e:
            logger.error(f"Failed to watch directory '{normalized_path}': {e}")

    def clear_watch(self, key: str):
        watch = self._watches.pop(key, None)
        self._paths.pop(key, None)

        if not watch:
            return

        try:
            self._observer.unschedule(watch)
        except Exception as e:
            logger.warning(f"Failed to unschedule watcher '{key}': {e}")

    def ignore_patterns(self, key: str, patterns: list[str]):
        """Register glob patterns whose matching paths are silently dropped.

        Patterns use ``pathlib.PurePath.match()`` semantics (``**/<name>``
        matches at any depth).  Typical callers pass patterns like
        ``["**/info.json", "**/properties.json"]`` so internal metadata
        writes never trigger a watched-directory refresh.
        """
        self._ignore_patterns[key] = list(patterns)

    def _should_ignore(self, key: str, src_path: str) -> bool:
        patterns = self._ignore_patterns.get(key)
        if not patterns:
            return False
        path = Path(src_path)
        return any(path.match(pattern) for pattern in patterns)

    def notify_changed(self, key: str, changed_path: str):
        self.directory_changed.emit(key, Path(changed_path))

    def is_suppressed(self, key: str) -> bool:
        return bool(self._suppression_tokens.get(key, 0))

    def suppress_watch(self, key: str, duration_ms: int = 5000):
        token = self._suppression_tokens.get(key, 0) + 1
        self._suppression_tokens[key] = token

        def clear_suppression():
            if self._suppression_tokens.get(key) == token:
                self._suppression_tokens.pop(key, None)

        QTimer.singleShot(duration_ms, clear_suppression)

    def stop(self):
        for key in list(self._watches):
            self.clear_watch(key)

        if self._observer.is_alive():
            self._observer.stop()
            self._observer.join(timeout=2)
