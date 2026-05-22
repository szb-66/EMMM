# App/services/thumbnail service.py


import os
import io
import time
from pathlib import Path
from collections import OrderedDict

from PyQt6.QtCore import QObject, pyqtSignal, QRunnable, QThreadPool
from PyQt6.QtGui import QPixmap

from PIL import Image, ImageFile

from app.utils.logger_utils import logger
from app.utils.async_utils import Worker

ImageFile.LOAD_TRUNCATED_IMAGES = True


class ThumbnailService(QObject):
    """
    Manages thumbnail loading, processing, and caching (memory and disk).
    Designed to be non-blocking and efficient for PyQt6.
    """

    thumbnail_generated = pyqtSignal(str, Path)

    L1_CACHE_MAX_SIZE = 100
    THUMBNAIL_TARGET_SIZE = (256, 256)
    JPEG_QUALITY = 85

    def __init__(self, cache_dir: Path, default_icons: dict[str, str]):
        super().__init__()
        # ---Service Setup ---
        self.cache_dir = cache_dir / "thumbnails"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # ---L1 Cache (In-Memory) ---
        self.memory_cache = OrderedDict()

        # ---Default Icons ---
        self.default_pixmaps = {
            name: QPixmap(str(path)) for name, path in default_icons.items()
        }

        # Dedicated thread pool for image processing
        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(2)

        self._processing_ids = set()

    def get_thumbnail(
        self, item_id: str, source_path: Path | None, default_type: str
    ) -> QPixmap:
        """
        Flow 2.2, 2.3, 5.2: The main method called by the UI. Returns a pixmap instantly.
        It checks caches first, otherwise returns a default icon and triggers a background load.
        """
        if not item_id:  # Cannot cache without a unique ID
            return self.default_pixmaps.get(default_type, QPixmap())

        # 1. L1 Cache Check (Memory)
        if pixmap := self.memory_cache.get(item_id):
            # logger.debug(f"L1 cache HIT for item '{item_id}'")
            self.memory_cache.move_to_end(item_id)  # Mark as recently used

            return pixmap

        # 2. L2 Cache Check (Disk)
        cache_path = self.cache_dir / f"{item_id}.jpg"
        if source_path and source_path.is_file() and cache_path.exists():
            try:
                if source_path.stat().st_mtime > cache_path.stat().st_mtime:
                    logger.info(f"Stale L2 cache for '{item_id}'. Will regenerate.")
                else:
                    #logger.debug(f"L2 cache HIT for item '{item_id}'")
                    pixmap = QPixmap(str(cache_path))
                    if not pixmap.isNull():
                        self._add_to_memory_cache(item_id, pixmap)  # Add to L1

                        return pixmap
            except FileNotFoundError:
                pass  # Source file might have been deleted, proceed to miss

        # 3. Cache Miss
        if source_path and source_path.is_file():
            self._queue_thumbnail_generation(item_id, source_path, cache_path)

        return self.default_pixmaps.get(default_type, QPixmap())

    def _queue_thumbnail_generation(
        self, item_id: str, source_path: Path, cache_path: Path
    ):
        """Starts a generic background worker to process an image."""
        if item_id in self._processing_ids:
            return

        self._processing_ids.add(item_id)

        # Use the generic Worker and pass the function and its arguments
        worker = Worker(self._process_and_cache_image, source_path, cache_path)

        worker.signals.result.connect(
            lambda result: self._on_generation_finished(item_id, result)
        )
        worker.signals.error.connect(
            lambda error, id=item_id: self._on_generation_error(id, error)
        )

        self.thread_pool.start(worker)

    def _add_to_memory_cache(self, key: str, pixmap: QPixmap):
        """Adds a new pixmap to the L1 memory cache and handles eviction."""
        if len(self.memory_cache) >= self.L1_CACHE_MAX_SIZE:
            # popitem(last=False) removes the oldest item (FIFO)
            oldest_key, _ = self.memory_cache.popitem(last=False)
            #logger.debug(f"L1 cache full. Evicting oldest item: {oldest_key}")

        self.memory_cache[key] = pixmap

    def _process_and_cache_image(
        self, source_path: Path, cache_path: Path
    ) -> dict | None:
        """
        [WORKER THREAD] Does the heavy lifting: opens, resizes, compresses,
        and saves the thumbnail to the L2 disk cache.
        Returns a dictionary with the resulting pixmap and cache path on success.
        """
        try:
            logger.debug(f"Generating thumbnail for '{source_path.name}'...")

            # Define processing parameters

            # 1. Open image using Pillow
            with Image.open(source_path) as image:
                # 2. Convert to RGB to handle formats like RGBA or P (paletted)
                #    JPEG does not support transparency.
                if image.mode not in ("RGB", "L"):  # L for grayscale
                    image = image.convert("RGB")

                # 3. Resize the image. .thumbnail() resizes in-place and preserves aspect ratio.
                image.thumbnail(self.THUMBNAIL_TARGET_SIZE, Image.Resampling.LANCZOS)

                # 4. Save to an in-memory buffer as a Progressive JPEG
                buffer = io.BytesIO()
                image.save(
                    buffer,
                    format="JPEG",
                    quality=self.JPEG_QUALITY,
                    optimize=True,
                    progressive=True,
                )
                buffer.seek(0)

                # 5. Write the buffer content to the L2 disk cache
                with open(cache_path, "wb") as f:
                    f.write(buffer.getvalue())

            # 6. Load the newly created cache file into a QPixmap
            pixmap = QPixmap(str(cache_path))
            if pixmap.isNull():
                logger.error(
                    f"Failed to create a valid QPixmap from cached file: {cache_path}"
                )
                return None

            logger.info(f"Successfully cached thumbnail to '{cache_path.name}'")

            # 7. Return the result
            return {"pixmap": pixmap, "cache_path": cache_path}

        except FileNotFoundError:
            logger.error(f"Source image not found during processing: {source_path}")
        except PermissionError:
            logger.error(f"Permission denied while processing image: {source_path}")
        except Exception as e:

            # Catch other potential Pillow/IO errors
            logger.critical(
                f"An unexpected error occurred during thumbnail processing for {source_path.name}: {e}",
                exc_info=True,
            )

        return None  # Return None on any failure

    def _on_generation_finished(self, item_id: str, result: dict | None):
        """
        [MAIN THREAD] Step 5: Handles the result from the worker.
        It updates the L1 cache and emits a signal to notify ViewModels.
        """
        # Delete the item from the list that is being processed
        self._processing_ids.discard(item_id)

        if not result or not result.get("pixmap"):
            logger.error(f"Thumbnail generation failed for item_id: {item_id}")
            return

        pixmap = result["pixmap"]
        cache_path = result["cache_path"]

        logger.info(f"Thumbnail generated for {item_id}. Updating L1 cache.")

        # 1. Add the newly made pixmap to the L1 cache (memory)
        self._add_to_memory_cache(item_id, pixmap)

        # 2. Pour out the signal that the new thumbnail has been made and stored on the disk
        #    This signal will be captured by the viewmodel
        self.thumbnail_generated.emit(item_id, cache_path)

    def _on_generation_error(self, item_id: str, error_info: tuple):
        """Handles worker errors and cleans up."""
        self._processing_ids.discard(item_id)
        logger.error(f"Error generating thumbnail for {item_id}: {error_info[1]}")

    def cleanup_disk_cache(self, max_age_days: int = 30, max_size_mb: int = 200):
        """
        [MAIN THREAD or WORKER] Step 6: Cleans up the L2 disk cache.
        Removes files older than `max_age_days`. If the cache size still
        exceeds `max_size_mb`, it removes the oldest files until the limit is met.
        """
        if not self.cache_dir.exists():
            return

        logger.info(f"Running disk cache cleanup for '{self.cache_dir}'...")

        try:
            files_to_scan = []
            total_size_bytes = 0
            # 1. Scan all files and gather their stats efficiently
            for entry in os.scandir(self.cache_dir):
                if entry.is_file():
                    try:
                        stat = entry.stat()
                        files_to_scan.append({"path": Path(entry.path), "stat": stat})
                        total_size_bytes += stat.st_size
                    except OSError:
                        continue  # Skip files that can't be accessed

            # --- Age-based cleanup ---
            age_limit_seconds = max_age_days * 86400
            current_time = time.time()

            # Keep only files that are NOT too old
            valid_files = []
            for file_info in files_to_scan:
                age = current_time - file_info["stat"].st_mtime
                if age > age_limit_seconds:
                    try:
                        os.remove(file_info["path"])
                        total_size_bytes -= file_info["stat"].st_size
                        logger.debug(
                            f"Removed old cache file: {file_info['path'].name}"
                        )
                    except OSError as e:
                        logger.warning(
                            f"Could not remove old cache file {file_info['path']}: {e}"
                        )
                else:
                    valid_files.append(file_info)

            # --- Size-based cleanup ---
            size_limit_bytes = max_size_mb * 1024 * 1024
            if total_size_bytes > size_limit_bytes:
                logger.info(
                    f"Cache size ({total_size_bytes / 1024**2:.2f}MB) exceeds limit ({max_size_mb}MB). Pruning oldest files."
                )

                # Sort remaining files by modification time (oldest first)
                valid_files.sort(key=lambda f: f["stat"].st_mtime)

                while total_size_bytes > size_limit_bytes and valid_files:
                    oldest_file = valid_files.pop(0)  # Get the oldest file
                    try:
                        file_size = oldest_file["stat"].st_size
                        os.remove(oldest_file["path"])
                        total_size_bytes -= file_size
                        logger.debug(
                            f"Pruned cache file by size: {oldest_file['path'].name}"
                        )
                    except OSError as e:
                        logger.warning(
                            f"Could not prune cache file {oldest_file['path']}: {e}"
                        )

            logger.info("Disk cache cleanup finished.")

        except Exception as e:
            logger.error(
                f"An unexpected error occurred during cache cleanup: {e}", exc_info=True
            )

    def invalidate_cache(self, item_id: str, path: Path | None = None):
        """
        Invalidates the cache for a specific item by removing it from both L1 and L2 caches.
        The L2 cache file is always identified by item_id, never by source path.
        """
        if not item_id:
            return

        # Remove from L1 cache
        if item_id in self.memory_cache:
            logger.debug(f"Invalidating L1 cache for item '{item_id}'")
            del self.memory_cache[item_id]

        # Remove from L2 cache (disk) — always by item_id, never by source path
        cache_path = self.cache_dir / f"{item_id}.jpg"
        if cache_path.exists():
            try:
                cache_path.unlink()
                logger.debug(f"Invalidated L2 cache for item '{item_id}'")
            except OSError as e:
                logger.error(f"Failed to remove cache file {cache_path}: {e}")
