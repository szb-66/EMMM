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
        if event.event_type in {"opened", "closed"}:
            return
        if self._owner.is_suppressed(self._key):
            logger.debug(f"Ignoring suppressed filesystem event for {self._key}: {event.src_path}")
            return
        self._owner.notify_changed(self._key, event.src_path)


class FileWatcherService(QObject):
    """Small watchdog wrapper that forwards directory changes through Qt signals."""

    directory_changed = pyqtSignal(str, object)

    def __init__(self):
        super().__init__()
        self._observer = Observer()
        self._observer.start()
        self._watches = {}
        self._paths = {}
        self._suppression_tokens = {}

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
                handler, str(normalized_path), recursive=False
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
