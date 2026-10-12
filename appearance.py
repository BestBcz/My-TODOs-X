"""The original SiliconUI visual language, shared by every application surface."""
from pathlib import Path

from PyQt5.QtCore import QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt, pyqtProperty
from PyQt5.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PyQt5.QtWidgets import QAbstractButton, QDialog, QHBoxLayout, QMessageBox as QtMessageBox, QPushButton, QToolButton, QVBoxLayout

LIGHT = dict(surface="#F3F3F3", field="#e8e8e8", border="#d0d0d0", title="#1f1f2f", description="#74747e",
             text="#41414f", muted="#8b8b94", icon="#0F85D3", accent="#0F85D3",
             transition_a="#2abed8", transition_b="#2ad98e", lever="#F3F3F3", switch_border="#bec1c7")
DARK = dict(surface="#252229", field="#1C191F", border="#3b373f", title="#FFFFFF", description="#96909d",
            text="#e1d9e8", muted="#96909d", icon="#e1d9e8", accent="#0F85D3",
            transition_a="#52389a", transition_b="#9c4e8b", lever="#100912", switch_border="#D2D2D2")

def palette(widget):
    current = widget
    while current is not None:
        value = current.property("darkTheme")
        if value is not None:
            return DARK if value else LIGHT
        current = current.parentWidget()
    return LIGHT

def text_font(size=14, bold=False):
    font = QFont("Microsoft YaHei")
    font.setPixelSize(size)
    font.setWeight(QFont.Bold if bold else QFont.Normal)
    return font

def stylesheet(dark=False):
    c = DARK if dark else LIGHT
    arrow = (Path(__file__).resolve().parent / "assets" / "ui" / ("chevron-dark.svg" if dark else "chevron-light.svg")).as_posix()
    return f"""
        QWidget {{ color: {c['text']}; font-family: 'Microsoft YaHei', 'Segoe UI'; font-size: 14px; }}
        QLabel {{ background: transparent; border: none; }}
        QLabel#cardTitle {{ color: {c['title']}; font-size: 20px; font-weight: 700; }}
        QLabel#settingTitle {{ color: {c['text']}; font-weight: 700; }}
        QLabel#settingDescription {{ color: {c['description']}; font-size: 14px; }}
        QLabel#sectionLabel {{ color: {c['muted']}; font-size: 12px; padding-top: 10px; }}
        QLabel#muted {{ color: {c['muted']}; font-size: 12px; }}
        QPushButton#headerCount {{ font-weight: 700; padding: 5px 10px; }}
        QPushButton#headerCount:checked {{ background: {'rgba(225,217,232,25)' if dark else 'rgba(15,133,211,25)'}; }}
        QPushButton#disclosure {{ color: {c['muted']}; text-align: left; padding: 4px 0; }}
        QPushButton#disclosure:hover {{ color: {c['icon']}; background: transparent; }}
        QFrame#card, QListView, QScrollArea, QStackedWidget {{ background: transparent; border: none; outline: none; }}
        QScrollArea > QWidget > QWidget {{ background: transparent; }}
        QLineEdit, QTextEdit, QComboBox, QDateTimeEdit {{
            background: {c['field']}; border: 1px solid {c['border']}; border-radius: 4px;
            padding: 7px 10px; selection-background-color: #0F85D3;
        }}
        QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QDateTimeEdit:focus {{ border-color: #0F85D3; }}
        QLineEdit#searchField {{ background: transparent; }}
        QTextEdit#reportPreview {{ background: transparent; border: none; padding: 0; }}
        QComboBox {{ padding-right: 26px; }}
        QComboBox[compact="true"] {{ background: transparent; border: none; padding: 5px 24px 5px 8px; }}
        QComboBox::drop-down, QDateTimeEdit::drop-down {{ border: none; width: 24px; }}
        QComboBox::down-arrow, QDateTimeEdit::down-arrow {{ image: url("{arrow}"); width: 10px; height: 10px; }}
        QComboBox QAbstractItemView {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 4px; padding: 6px; selection-background-color: {'#3b343f' if dark else '#dfeaf2'}; selection-color: {c['text']}; outline: none; }}
        QPushButton, QToolButton {{ background: transparent; border: none; border-radius: 4px; padding: 6px 12px; }}
        QPushButton:hover, QToolButton:hover {{ background: {'#39333f' if dark else '#e2e9ef'}; }}
        QPushButton:pressed, QToolButton:pressed {{ background: {'#443b4b' if dark else '#d1e2ed'}; }}
        QPushButton:disabled, QCheckBox:disabled {{ color: {c['muted']}; }}
        QPushButton#primary {{ background: {'#403347' if dark else '#d9eaf5'}; color: {c['text']}; font-weight: 700; }}
        QCheckBox {{ spacing: 8px; background: transparent; padding: 3px 0; }}
        QCheckBox::indicator {{ width: 18px; height: 18px; border: 1px solid {c['muted']}; border-radius: 4px; background: transparent; }}
        QCheckBox::indicator:checked {{ background: {c['icon']}; border-color: {c['icon']}; image: url("{(Path(__file__).resolve().parent / 'assets/ui/check.svg').as_posix()}"); }}
        QSlider::groove:horizontal {{ height: 4px; background: {c['border']}; border-radius: 2px; }}
        QSlider::sub-page:horizontal {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {c['transition_a']},stop:1 {c['transition_b']}); border-radius: 2px; }}
        QSlider::handle:horizontal {{ width: 14px; margin: -5px 0; background: {c['text']}; border-radius: 7px; }}
        QScrollBar:vertical {{ width: 6px; background: transparent; margin: 4px 0; }}
        QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 3px; min-height: 28px; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
        QMenu {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 6px; padding: 6px; }}
        QMenu::item {{ padding: 8px 24px; border-radius: 4px; }}
        QMenu::item:selected {{ background: {'#39333f' if dark else '#e2e9ef'}; }}
        QToolTip {{ background: {c['surface']}; color: {c['text']}; border: 1px solid {c['border']}; padding: 8px; }}
        QCalendarWidget QWidget {{ background: {c['surface']}; }}
        QCalendarWidget QAbstractItemView {{ background: {c['surface']}; color: {c['text']}; selection-background-color: #0F85D3; selection-color: white; }}
    """

class IconButton(QToolButton):
    """Small SiliconUI-style glyph with a bounded, quiet hover animation."""
    def __init__(self, name, hint, callback, parent=None):
        super().__init__(parent)
        self.icon_name = name
        self._hover = 0.0
        self._keyboard_focus = False
        self.motion = QPropertyAnimation(self, b"hoverProgress", self)
        self.motion.setDuration(140)
        self.motion.setEasingCurve(QEasingCurve.OutCubic)
        self.setFixedSize(32, 32)
        self.setIconSize(QSize(16, 16))
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(hint)
        self.setAccessibleName(hint)
        self.clicked.connect(callback)

    @pyqtProperty(float)
    def hoverProgress(self): return self._hover
    @hoverProgress.setter
    def hoverProgress(self, value):
        self._hover = value
        self.update()

    def transition(self, value):
        self.motion.stop()
        self.motion.setStartValue(self._hover)
        self.motion.setEndValue(value)
        self.motion.start()

    def enterEvent(self, event):
        self.transition(1.0)
        super().enterEvent(event)
    def leaveEvent(self, event):
        self.transition(0.0)
        super().leaveEvent(event)
    def hideEvent(self, event):
        self.motion.stop()
        self._hover = 0.0
        super().hideEvent(event)

    def focusInEvent(self, event):
        self._keyboard_focus = event.reason() in (Qt.TabFocusReason, Qt.BacktabFocusReason, Qt.ShortcutFocusReason)
        super().focusInEvent(event)

    def paintEvent(self, event):
        from widgets import icon
        c = palette(self)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        opacity = 0.1 if self.isChecked() else 0.0
        opacity += self._hover * .06 + (.06 if self.isDown() else 0)
        color = QColor(c["icon"])
        color.setAlphaF(opacity)
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(QRectF(self.rect()), 4, 4)
        if not self.isEnabled(): painter.setOpacity(.35)
        icon(self.icon_name, c["icon"]).paint(painter, self.rect().adjusted(8, 8, -8, -8))
        if self.hasFocus() and self._keyboard_focus:
            painter.setPen(QPen(QColor(c["accent"]), 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(QRectF(self.rect().adjusted(1,1,-1,-1)), 4, 4)

class SiliconSwitch(QAbstractButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(40, 20)
        self.setCursor(Qt.PointingHandCursor)
        self._position = 0.0
        self.motion = QPropertyAnimation(self, b"leverPosition", self)
        self.motion.setDuration(170)
        self.motion.setEasingCurve(QEasingCurve.OutCubic)
        self.toggled.connect(self.transition)

    @pyqtProperty(float)
    def leverPosition(self): return self._position
    @leverPosition.setter
    def leverPosition(self, value):
        self._position = value
        self.update()

    def setChecked(self, value):
        changed = self.isChecked() != value
        super().setChecked(value)
        if changed: self.transition(value)

    def transition(self, checked):
        self.motion.stop()
        target = 1.0 if checked else 0.0
        if not self.isVisible():
            self.leverPosition = target
            return
        self.motion.setStartValue(self._position)
        self.motion.setEndValue(target)
        self.motion.start()

    def hideEvent(self, event):
        self.motion.stop()
        self.leverPosition = float(self.isChecked())
        super().hideEvent(event)

    def paintEvent(self, event):
        c = palette(self)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if not self.isEnabled(): p.setOpacity(.35)
        rect = QRectF(.5, .5, 39, 19)
        p.setPen(QPen(QColor(c["switch_border"]), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(rect, 10, 10)
        if self._position:
            gradient = QLinearGradient(0, 0, 40, 20)
            gradient.setColorAt(0, QColor(c["transition_a"]))
            gradient.setColorAt(1, QColor(c["transition_b"]))
            p.setOpacity(p.opacity() * self._position)
            p.setPen(Qt.NoPen)
            p.setBrush(gradient)
            p.drawRoundedRect(rect, 10, 10)
            p.setOpacity(1.0 if self.isEnabled() else .35)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(c["lever"] if self._position >= .5 else c["switch_border"]))
        p.drawEllipse(QRectF(3 + 20*self._position, 3, 14, 14))

class SiliconDialog(QDialog):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        from widgets import Card, tool_button
        dark = palette(parent) is DARK if parent else False
        self.setProperty("darkTheme", dark)
        self.setWindowTitle(title)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(stylesheet(dark))
        self.setFont(text_font())
        self.setMinimumWidth(380)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        self.card = Card(title, self)
        self.card.header_layout.addWidget(tool_button("close", "关闭", self.reject))
        outer.addWidget(self.card)
        self.body = self.card.layout_v
        self._anchor = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.pos().y() < 84:
            if not self.windowHandle() or not self.windowHandle().startSystemMove():
                self._anchor = event.globalPos()-self.pos()
        super().mousePressEvent(event)
    def mouseMoveEvent(self, event):
        if self._anchor is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPos()-self._anchor)
        super().mouseMoveEvent(event)
    def mouseReleaseEvent(self, event):
        self._anchor = None
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        for inset in range(2, 18, 2):
            p.setBrush(QColor(0, 0, 0, 4))
            p.drawRoundedRect(QRectF(self.rect().adjusted(inset,inset,-inset,-inset)), 10, 10)

class MessageBox:
    Yes, No, Save, Discard, Cancel = QtMessageBox.Yes, QtMessageBox.No, QtMessageBox.Save, QtMessageBox.Discard, QtMessageBox.Cancel
    @staticmethod
    def show(parent, title, text, buttons, default=None):
        from PyQt5.QtWidgets import QLabel
        dialog = SiliconDialog(title, parent)
        label = QLabel(str(text))
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        dialog.body.addWidget(label)
        row = QHBoxLayout()
        row.setContentsMargins(0, 16, 0, 0)
        row.addStretch()
        result = [MessageBox.Cancel]
        for value, caption in ((MessageBox.Yes, "确定"), (MessageBox.No, "取消"), (MessageBox.Save, "保存"), (MessageBox.Discard, "放弃修改"), (MessageBox.Cancel, "取消")):
            if buttons & value:
                button = QPushButton(caption)
                def choose(checked=False, choice=value):
                    result[0] = choice
                    dialog.accept()
                button.clicked.connect(choose)
                if value == default:
                    button.setObjectName("primary")
                    button.setDefault(True)
                row.addWidget(button)
        dialog.body.addLayout(row)
        dialog.exec_()
        return result[0]
    @staticmethod
    def question(parent, title, text, buttons=Yes|No, default=None):
        return MessageBox.show(parent, title, text, buttons, default)
    @staticmethod
    def warning(parent, title, text): return MessageBox.show(parent, title, text, MessageBox.Yes, MessageBox.Yes)
    information = warning
    critical = warning

def get_text(parent, title, prompt, text=""):
    from PyQt5.QtWidgets import QLabel, QLineEdit
    dialog = SiliconDialog(title, parent)
    dialog.body.addWidget(QLabel(prompt))
    field = QLineEdit(text)
    dialog.body.addWidget(field)
    row = QHBoxLayout()
    row.addStretch()
    cancel, save = QPushButton("取消"), QPushButton("确定")
    cancel.clicked.connect(dialog.reject)
    save.setObjectName("primary")
    save.setDefault(True)
    save.clicked.connect(dialog.accept)
    row.addWidget(cancel)
    row.addWidget(save)
    dialog.body.addLayout(row)
    field.selectAll()
    field.setFocus()
    accepted = dialog.exec_() == QDialog.Accepted
    return field.text(), accepted
