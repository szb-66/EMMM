# app/views/components/sync_candidate_widget.py

from pathlib import Path
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout
from qfluentwidgets import BodyLabel, CaptionLabel, AvatarWidget

from app.core import i18n as _i18n
from app.services.thumbnail_service import ThumbnailService
from app.services.database_service import DatabaseService
from app.utils.logger_utils import logger

class SyncCandidateWidget(QWidget):
    """
    [CORRECTED] A widget to display a single database sync candidate.
    It now handles its own thumbnail updates correctly to prevent race conditions.
    """

    def __init__(self, candidate_data: dict, game_type: str, thumbnail_service: ThumbnailService, database_service: DatabaseService, parent: QWidget | None = None):
        super().__init__(parent)
        self.candidate_data = candidate_data
        self.game_type = game_type
        self.thumbnail_service = thumbnail_service
        self.database_service = database_service

        self.item_id = self.candidate_data.get("name", "")

        self._init_ui()
        self._populate_data()

        # Connect to the service's signal to receive the thumbnail path when it's ready
        self.thumbnail_service.thumbnail_generated.connect(self._on_thumbnail_ready)

    def _init_ui(self):
        """Initializes the UI components of the widget."""
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 8, 12, 8)
        main_layout.setSpacing(16)

        self.thumbnail_label = AvatarWidget(self)
        self.thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.thumbnail_label.setRadius(16)
        self.thumbnail_label.setFixedSize(QSize(36, 36))
        main_layout.addWidget(self.thumbnail_label)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(0)
        text_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.name_label = BodyLabel()
        self.details_label = CaptionLabel()
        # make detail_label lower opacity
        self.details_label.setStyleSheet("opacity: 0.7;color: #888888;")


        text_layout.addWidget(self.name_label)
        text_layout.addWidget(self.details_label)
        # add margin bottom
        text_layout.setContentsMargins(0, 0, 0, 4)

        main_layout.addLayout(text_layout, 1)

    def _populate_data(self):
        """Fills the widget with data and requests the thumbnail."""
        self.name_label.setText(self.candidate_data.get("name", _i18n.tr("failure_report.unknown")))

        rarity_alias = self.database_service.get_alias_for_game(self.game_type, 'rarity', fallback="Rarity")
        element_alias = self.database_service.get_alias_for_game(self.game_type, 'element', fallback="Element")

        rarity = self.candidate_data.get("rarity", "N/A")
        element = self.candidate_data.get("element", "N/A")
        self.details_label.setText(_i18n.tr("sync_candidate.details", rarity_alias=rarity_alias, rarity=rarity, element_alias=element_alias, element=element))

        thumb_path_str = self.candidate_data.get("thumbnail_path")
        thumb_path = Path(thumb_path_str) if thumb_path_str else None

        pixmap = self.thumbnail_service.get_thumbnail(
            item_id=self.item_id,
            source_path=thumb_path,
            default_type='object'
        )
        self.thumbnail_label.setPixmap(pixmap)
        self.thumbnail_label.setRadius(16)
        self.thumbnail_label.setFixedSize(QSize(36, 36))

    def _on_thumbnail_ready(self, item_id: str, cache_path: Path):
        """
        [CORRECTED] Slot to receive the generated thumbnail's PATH from the service.
        """
        # Check if the signal is for this specific widget instance
        if item_id == self.item_id:
            logger.debug(f"Received thumbnail for '{item_id}' at path: {cache_path}")
            # Create the QPixmap object FROM the provided path
            pixmap = QPixmap(str(cache_path))
            if not pixmap.isNull():
                self.thumbnail_label.setPixmap(pixmap)
                self.thumbnail_label.setRadius(16)
                self.thumbnail_label.setFixedSize(QSize(36, 36))

            # Disconnect after receiving the thumbnail to prevent unnecessary updates
            try:
                self.thumbnail_service.thumbnail_generated.disconnect(self._on_thumbnail_ready)
            except TypeError:
                # This can happen if the signal is already disconnected, which is fine.
                pass

    def closeEvent(self, event):
        """Ensure signal is disconnected when the widget is closed to prevent memory leaks."""
        try:
            self.thumbnail_service.thumbnail_generated.disconnect(self._on_thumbnail_ready)
        except TypeError:
            pass # Signal might already be disconnected
        super().closeEvent(event)