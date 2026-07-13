# app/views/dialogs/password_dialog.py

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout
from qfluentwidgets import PasswordLineEdit, PrimaryPushButton, PushButton, BodyLabel

from app.core import i18n as _i18n

class PasswordDialog(QDialog):
    """A simple dialog to ask the user for an archive password."""
    def __init__(self, archive_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_i18n.tr("password.title"))

        self.info_label = BodyLabel(_i18n.tr("password.info", name=archive_name), self)
        self.password_edit = PasswordLineEdit(self)

        ok_button = PrimaryPushButton(_i18n.tr("common.ok"))
        cancel_button = PushButton(_i18n.tr("common.cancel"))

        layout = QVBoxLayout(self)
        button_layout = QHBoxLayout()
        button_layout.addStretch(1)
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(ok_button)

        layout.addWidget(self.info_label)
        layout.addWidget(self.password_edit)
        layout.addLayout(button_layout)

        ok_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)
        self.password_edit.returnPressed.connect(self.accept)

    def get_password(self) -> str:
        return self.password_edit.text()
