"""Tracer-bullet tests for FileWatcherService ignore_patterns.

Verifies that the file watcher can filter out file-system events for paths
matching configured patterns (e.g. ``info.json``, ``properties.json``) so
internal metadata writes don't trigger full UI refreshes.
"""

import tempfile
import time
import unittest
from pathlib import Path

from PyQt6.QtCore import QThreadPool
from PyQt6.QtWidgets import QApplication

from app.services.file_watcher_service import FileWatcherService

_qapp = None


def setUpModule():
    global _qapp
    _qapp = QApplication.instance()
    if _qapp is None:
        _qapp = QApplication(["FileWatcherServiceTests"])


class FileWatcherIgnorePatternsTests(unittest.TestCase):
    """Integration-style tests for the ignore_patterns feature.

    Each test creates a real temp directory, starts a watchdog observer on it,
    writes files, and checks which paths were emitted via the
    ``directory_changed`` signal.
    """

    def setUp(self):
        self.service = FileWatcherService()

    def tearDown(self):
        self.service.stop()
        # Give the observer thread a moment to join so the next test's
        # TemporaryDirectory cleanup doesn't race with pending events.
        QThreadPool.globalInstance().waitForDone()

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------
    @staticmethod
    def _collect_events(service, key, tmp_path, action_fn, *, settle_ms=600):
        """Execute *action_fn* while collecting ``directory_changed`` events."""
        collected = []

        def on_changed(k: str, p: Path):
            collected.append((k, p.name))

        service.directory_changed.connect(on_changed)
        # Give watchdog a moment to install the directory handle before
        # we start writing files (especially important on Windows).
        time.sleep(0.15)
        action_fn(tmp_path)
        # Allow the watchdog thread to pick up and emit the event.
        time.sleep(settle_ms / 1000.0)
        # Process Qt events so queued signal emissions are delivered.
        QApplication.processEvents()
        try:
            service.directory_changed.disconnect(on_changed)
        except TypeError:
            pass
        return collected

    # ------------------------------------------------------------------
    # Tracer Bullet #1 — JSON files are ignored, INI files are not
    # ------------------------------------------------------------------
    def test_json_files_ignored_ini_files_emitted(self):
        """``info.json`` and ``properties.json`` modifications should NOT
        trigger ``directory_changed``, but ``.ini`` changes should."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.service.ignore_patterns("test_key", ["**/info.json", "**/properties.json"])
            self.service.watch_directory("test_key", root)

            def write_files(p: Path):
                (p / "info.json").write_text('{"key": "val"}', encoding="utf-8")
                (p / "properties.json").write_text('{}', encoding="utf-8")
                (p / "merged.ini").write_text("[Section]\nkey = 1\n", encoding="utf-8")

            events = self._collect_events(self.service, "test_key", root, write_files)

            emitted_names = {name for _, name in events}
            self.assertNotIn("info.json", emitted_names,
                             "info.json should be ignored by pattern filter")
            self.assertNotIn("properties.json", emitted_names,
                             "properties.json should be ignored by pattern filter")
            self.assertIn("merged.ini", emitted_names,
                          "merged.ini should still trigger an event")

    # ------------------------------------------------------------------
    # Tracer Bullet #2 — ignore_patterns is scoped per key
    # ------------------------------------------------------------------
    def test_ignore_patterns_are_scoped_per_watch_key(self):
        """Patterns registered for key-A must not affect events for key-B."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dir_a = root / "A"
            dir_b = root / "B"
            dir_a.mkdir()
            dir_b.mkdir()

            self.service.ignore_patterns("key_a", ["**/info.json"])
            self.service.watch_directory("key_a", dir_a)
            self.service.watch_directory("key_b", dir_b)

            events_a = []
            events_b = []

            def on_changed_a(k, p):
                events_a.append((k, p.name))

            def on_changed_b(k, p):
                events_b.append((k, p.name))

            self.service.directory_changed.connect(on_changed_a)
            # Hmm — we can only distinguish by key in the collector.
            # Let's use a single collector that tracks key.
            self.service.directory_changed.disconnect(on_changed_a)

            collected = {}

            def track(k: str, p: Path):
                collected.setdefault(k, []).append(p.name)

            self.service.directory_changed.connect(track)

            time.sleep(0.15)  # let watchdog install handles
            (dir_a / "info.json").write_text("{}", encoding="utf-8")
            (dir_b / "info.json").write_text("{}", encoding="utf-8")
            time.sleep(0.45)
            QApplication.processEvents()

            try:
                self.service.directory_changed.disconnect(track)
            except TypeError:
                pass

            # key_a has ignore_patterns → info.json should NOT appear
            self.assertNotIn("info.json", collected.get("key_a", []),
                             "key_a has ignore_patterns for info.json")
            # key_b has NO ignore_patterns → info.json SHOULD appear
            self.assertIn("info.json", collected.get("key_b", []),
                          "key_b has no ignore patterns, info.json should emit")


if __name__ == "__main__":
    unittest.main()
