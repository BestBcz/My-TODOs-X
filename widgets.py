"""Lightweight Qt widgets and a virtualized, wrapping task list."""
from datetime import datetime, timedelta
from pathlib import Path
from functools import lru_cache

from PyQt5.QtCore import QAbstractListModel, QByteArray, QDate, QDateTime, QEvent, QMimeData, QModelIndex, QPoint, QRect, QRectF, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QDrag, QFont, QIcon, QKeySequence, QPainter, QPixmap, QTextDocument
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import QApplication, QCheckBox, QComboBox, QDateEdit, QDateTimeEdit, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QLayout, QListView, QMessageBox, QPushButton, QShortcut, QSizePolicy, QStyle, QStyledItemDelegate, QTextEdit, QToolButton, QVBoxLayout
from task_store import UNCATEGORIZED, stamp

SVG_PATHS = {
    "add": "M12 5v14M5 12h14", "close": "M6 6l12 12M18 6L6 18",
    "settings": "M4 7h16M4 12h16M4 17h16M8 5v4M16 10v4M10 15v4",
    "pin": "M8 3h8l-1 6 4 4H5l4-4zM12 13v8",
    "more": "M5 12h.01M12 12h.01M19 12h.01",
    "calendar": "M5 5h14v15H5zM8 3v4M16 3v4M5 10h14M8 15l3 3 5-5",
    "back": "M14 5l-7 7 7 7M7 12h13",
}

@lru_cache(maxsize=64)
def icon(name, color="#0F85D3"):
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="{SVG_PATHS[name]}" fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>'
    result, renderer = QIcon(), QSvgRenderer(QByteArray(svg.encode()))
    for size in (16, 24, 32, 48, 64, 128, 256):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        result.addPixmap(pixmap)
    return result

def tool_button(name, hint, callback):
    button = QToolButton()
    button.setObjectName("iconButton")
    button.setIcon(icon(name))
    button.setToolTip(hint)
    button.setAccessibleName(hint)
    button.setFixedSize(32, 32)
    button.clicked.connect(callback)
    return button

class FlowLayout(QLayout):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = []
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(8)
    def addItem(self, item): self.items.append(item)
    def count(self): return len(self.items)
    def itemAt(self, index): return self.items[index] if 0 <= index < len(self.items) else None
    def takeAt(self, index): return self.items.pop(index) if 0 <= index < len(self.items) else None
    def expandingDirections(self): return Qt.Orientations(0)
    def hasHeightForWidth(self): return True
    def heightForWidth(self, width): return self._layout(QRect(0, 0, width, 0), True)
    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._layout(rect, False)
    def sizeHint(self): return self.minimumSize()
    def minimumSize(self):
        size = QSize()
        for item in self.items: size = size.expandedTo(item.minimumSize())
        return size
    def _layout(self, rect, measure):
        x, y, height = rect.x(), rect.y(), 0
        for item in self.items:
            size = item.sizeHint()
            if x > rect.x() and x + size.width() > rect.right() + 1:
                x, y, height = rect.x(), y + height + self.spacing(), 0
            if not measure: item.setGeometry(QRect(QPoint(x, y), size))
            x += size.width() + self.spacing()
            height = max(height, size.height())
        return y + height - rect.y()

class Card(QFrame):
    def __init__(self, title=None, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.layout_v = QVBoxLayout(self)
        self.layout_v.setContentsMargins(16, 16, 16, 16)
        self.layout_v.setSpacing(12)
        if title:
            label = QLabel(title)
            label.setObjectName("cardTitle")
            self.layout_v.addWidget(label)

class TaskModel(QAbstractListModel):
    reordered = pyqtSignal(object)
    MIME = "application/x-mytodos-task"
    def __init__(self, parent=None):
        super().__init__(parent)
        self.tasks, self.can_reorder = [], True
    def rowCount(self, parent=QModelIndex()): return 0 if parent.isValid() else len(self.tasks)
    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self.tasks): return None
        task = self.tasks[index.row()]
        if role in (Qt.DisplayRole, Qt.AccessibleTextRole): return task.text
        if role == Qt.UserRole: return task
        if role == Qt.CheckStateRole: return Qt.Checked if task.status == "completed" else Qt.Unchecked
        return None
    def flags(self, index):
        if not index.isValid(): return Qt.ItemIsDropEnabled if self.can_reorder else Qt.NoItemFlags
        flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        return flags | Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled if self.can_reorder else flags
    def set_tasks(self, tasks, can_reorder):
        self.beginResetModel()
        self.tasks, self.can_reorder = tasks, can_reorder
        self.endResetModel()
    def supportedDropActions(self): return Qt.MoveAction
    def mimeTypes(self): return [self.MIME]
    def mimeData(self, indexes):
        mime = QMimeData()
        if indexes: mime.setData(self.MIME, self.tasks[indexes[0].row()].id.encode())
        return mime
    def dropMimeData(self, mime, action, row, column, parent):
        if action == Qt.IgnoreAction: return True
        if not self.can_reorder or not mime.hasFormat(self.MIME): return False
        task_id = bytes(mime.data(self.MIME)).decode()
        ids = [t.id for t in self.tasks]
        if task_id not in ids: return False
        target = row if row >= 0 else parent.row() if parent.isValid() else len(ids)
        original = ids.index(task_id)
        ids.pop(original)
        if target > original: target -= 1
        ids.insert(max(0, min(target, len(ids))), task_id)
        pinned = {t.id for t in self.tasks if t.pinned}
        if set(ids[:len(pinned)]) != pinned: return False
        self.reordered.emit(ids)
        return True

class TaskListView(QListView):
    """Own the drag lifecycle: a database reorder never deletes a source row."""
    def startDrag(self, supported_actions):
        index = self.currentIndex()
        if not index.isValid() or not self.model().can_reorder: return
        drag = QDrag(self)
        drag.setMimeData(self.model().mimeData([index]))
        drag.setPixmap(self.viewport().grab(self.visualRect(index)))
        drag.exec_(Qt.MoveAction)

    def dropEvent(self, event):
        model = self.model()
        if not model.can_reorder or not event.mimeData().hasFormat(model.MIME):
            event.ignore()
            return
        index = self.indexAt(event.pos())
        row = model.rowCount()
        if index.isValid():
            row = index.row() + (event.pos().y() >= self.visualRect(index).center().y())
        if model.dropMimeData(event.mimeData(), Qt.MoveAction, row, 0, QModelIndex()):
            event.setDropAction(Qt.MoveAction)
            event.accept()
        else: event.ignore()

class TaskDelegate(QStyledItemDelegate):
    toggled = pyqtSignal(str)
    menu_requested = pyqtSignal(str, object)
    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window, self.cache = window, {}
    def document(self, task, width):
        key = (task.id, task.text, width, task.status)
        if key not in self.cache:
            doc = QTextDocument()
            font = QFont(self.window.font())
            font.setStrikeOut(task.status == "completed")
            doc.setDefaultFont(font)
            doc.setDocumentMargin(0)
            doc.setPlainText(task.text)
            doc.setTextWidth(max(50, width - 76))
            if len(self.cache) > max(100, len(self.window.model.tasks) * 2): self.cache.clear()
            self.cache[key] = doc
        return self.cache[key]
    def sizeHint(self, option, index):
        task = index.data(Qt.UserRole)
        width = self.window.list_view.viewport().width()
        return QSize(width, max(60, int(self.document(task, width).size().height()) + 42))
    def paint(self, painter, option, index):
        task, rect = index.data(Qt.UserRole), option.rect
        dark = self.window.settings.get("dark_mode")
        text, muted = QColor("#e1d9e8" if dark else "#353343"), QColor("#a19aaa" if dark else "#777384")
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        hovered = bool(option.state & (QStyle.State_Selected | QStyle.State_MouseOver))
        if hovered:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#34303b" if dark else "#e5edf6"))
            painter.drawRoundedRect(QRectF(rect.adjusted(0, 2, 0, -2)), 6, 6)
        check = QRectF(rect.left()+6, rect.top()+13, 16, 16)
        painter.setPen(QColor("#0F85D3") if task.status == "completed" else muted)
        painter.setBrush(QColor("#0F85D3") if task.status == "completed" else QColor(0, 0, 0, 0))
        painter.drawRoundedRect(check, 4, 4)
        if task.status == "completed":
            painter.setPen(QColor("white"))
            painter.drawLine(QPoint(int(check.x()+3), int(check.y()+8)), QPoint(int(check.x()+7), int(check.y()+12)))
            painter.drawLine(QPoint(int(check.x()+7), int(check.y()+12)), QPoint(int(check.x()+13), int(check.y()+4)))
        doc = self.document(task, rect.width())
        painter.translate(rect.left()+32, rect.top()+10)
        context = doc.documentLayout().PaintContext()
        context.palette.setColor(context.palette.Text, muted if task.status == "completed" else text)
        doc.documentLayout().draw(painter, context)
        painter.translate(-rect.left()-32, -rect.top()-10)
        metadata = []
        if task.pinned: metadata.append("置顶")
        if task.priority != 1: metadata.append("高优先级" if task.priority == 2 else "低优先级")
        if task.category_id != UNCATEGORIZED: metadata.append(self.window.category_names.get(task.category_id, "未分类"))
        if task.due_at:
            dt = datetime.fromisoformat(task.due_at).astimezone()
            metadata.append(("逾期 " if task.status == "active" and dt < datetime.now().astimezone() else "") + dt.strftime("%m-%d %H:%M"))
        if task.remind_at: metadata.append("已提醒" if task.reminder_sent_at else "有提醒")
        painter.setPen(muted)
        small = QFont(self.window.font())
        small.setPointSizeF(max(8, small.pointSizeF()-1))
        painter.setFont(small)
        meta_rect = rect.adjusted(32, rect.height()-27, -36, -5)
        painter.drawText(meta_rect, Qt.AlignLeft | Qt.AlignVCenter,
                         painter.fontMetrics().elidedText(" · ".join(metadata), Qt.ElideRight, meta_rect.width()))
        if hovered: icon("more", muted.name()).paint(painter, QRect(rect.right()-30, rect.top()+10, 24, 24))
        painter.setPen(QColor("#3b373f" if dark else "#e4e1e8"))
        painter.drawLine(rect.bottomLeft()+QPoint(32, 0), rect.bottomRight()-QPoint(8, 0))
        painter.restore()
    def editorEvent(self, event, model, option, index):
        task = index.data(Qt.UserRole)
        if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            if event.pos().x() < option.rect.left()+30 and not task.trashed:
                self.toggled.emit(task.id)
                return True
            if event.pos().x() > option.rect.right()-36:
                self.menu_requested.emit(task.id, event.globalPos())
                return True
        return super().editorEvent(event, model, option, index)

class TaskEditor(Card):
    saved, cancelled = pyqtSignal(), pyqtSignal()
    def __init__(self, window):
        super().__init__("添加待办")
        self.host, self.task, self.baseline = window, None, None
        self.title = self.layout_v.itemAt(0).widget()
        self.text = QTextEdit()
        self.text.setPlaceholderText("请输入待办内容，支持多行…")
        self.text.setMinimumHeight(100)
        self.text.setAcceptRichText(False)
        self.layout_v.addWidget(self.text)
        row = QHBoxLayout()
        self.category = QComboBox()
        self.category.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.category.setMinimumContentsLength(6)
        self.category.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row.addWidget(QLabel("分类"))
        row.addWidget(self.category, 1)
        row.addWidget(tool_button("add", "新建分类", window.add_category))
        self.layout_v.addLayout(row)
        self.priority, self.pinned = QComboBox(), QCheckBox("事项置顶")
        for label, value in (("高", 2), ("中", 1), ("低", 0)): self.priority.addItem(label, value)
        row = QHBoxLayout()
        row.addWidget(QLabel("优先级"))
        row.addWidget(self.priority)
        row.addStretch()
        row.addWidget(self.pinned)
        self.layout_v.addLayout(row)
        self.due_enabled, self.due = self.date_field("截止时间")
        self.remind_enabled, self.remind = self.date_field("独立提醒")
        note = QLabel("后台运行时提醒；退出期间错过的提醒会在下次启动时补发。")
        note.setObjectName("muted")
        note.setWordWrap(True)
        self.layout_v.addWidget(note)
        row = QHBoxLayout()
        cancel, save = QPushButton("取消"), QPushButton("保存")
        cancel.clicked.connect(self.cancelled)
        save.setObjectName("primary")
        save.clicked.connect(self.save)
        row.addStretch()
        row.addWidget(cancel)
        row.addWidget(save)
        self.layout_v.addLayout(row)
        shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        shortcut.activated.connect(self.save)
    def date_field(self, label):
        row, enabled, edit = QHBoxLayout(), QCheckBox(label), QDateTimeEdit()
        edit.setCalendarPopup(True)
        edit.setDisplayFormat("yyyy-MM-dd HH:mm")
        edit.setMinimumWidth(170)
        enabled.toggled.connect(edit.setEnabled)
        row.addWidget(enabled)
        row.addWidget(edit, 1)
        self.layout_v.addLayout(row)
        return enabled, edit
    def reload_categories(self):
        current = self.category.currentData()
        self.category.clear()
        for key, name in self.host.store.categories(): self.category.addItem(name, key)
        self.category.setCurrentIndex(max(0, self.category.findData(current)))
    def open(self, task=None):
        self.task = task
        self.title.setText("修改待办" if task else "添加待办")
        self.reload_categories()
        self.text.setPlainText(task.text if task else "")
        self.category.setCurrentIndex(max(0, self.category.findData(task.category_id if task else UNCATEGORIZED)))
        self.priority.setCurrentIndex(self.priority.findData(task.priority if task else 1))
        self.pinned.setChecked(task.pinned if task else False)
        for enabled, edit, value in ((self.due_enabled, self.due, task.due_at if task else None),
                                     (self.remind_enabled, self.remind, task.remind_at if task else None)):
            edit.setDateTime(QDateTime(datetime.fromisoformat(value).astimezone().replace(tzinfo=None)) if value else QDateTime.currentDateTime().addSecs(3600))
            enabled.setChecked(bool(value))
            edit.setEnabled(bool(value))
        self.baseline = self.fields()
        self.text.setFocus()
    def fields(self):
        def selected(enabled, edit, original):
            if not enabled.isChecked(): return None
            if original and edit.dateTime() == QDateTime(datetime.fromisoformat(original).astimezone().replace(tzinfo=None)):
                return original
            return stamp(edit.dateTime().toPyDateTime().astimezone())
        return {"text": self.text.toPlainText(), "category_id": self.category.currentData(),
                "priority": self.priority.currentData(), "pinned": self.pinned.isChecked(),
                "due_at": selected(self.due_enabled, self.due, self.task.due_at if self.task else None),
                "remind_at": selected(self.remind_enabled, self.remind, self.task.remind_at if self.task else None)}
    def dirty(self): return self.baseline is not None and self.fields() != self.baseline
    def save(self):
        fields = self.fields()
        reminder = fields["remind_at"]
        original = self.task.remind_at if self.task else None
        # Editing another field must not re-arm an already elapsed reminder.
        if reminder and reminder != original and reminder <= stamp(datetime.now().astimezone()):
            self.host.show_error("请选择未来的提醒时间。")
            return False
        try:
            if self.task: self.host.store.update(self.task.id, **fields)
            else: self.host.store.add(**fields)
        except Exception as exc:
            self.host.show_error(f"事项未保存：{exc}")
            return False
        self.baseline = None
        self.saved.emit()
        return True

class WeeklyReportDialog(QDialog):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("每周总结 · My-TODOs-X")
        self.resize(620, 560)
        self.setMinimumSize(380, 320)
        layout, row = QVBoxLayout(self), QHBoxLayout()
        row.addWidget(QLabel("选择周内任意一天"))
        self.date = QDateEdit(QDate.currentDate())
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("yyyy-MM-dd")
        self.date.setMaximumDate(QDate.currentDate())
        self.date.dateChanged.connect(self.refresh)
        row.addWidget(self.date)
        row.addStretch()
        layout.addLayout(row)
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        layout.addWidget(self.preview, 1)
        row = QHBoxLayout()
        copy, export, close = QPushButton("复制周报"), QPushButton("导出 Markdown"), QPushButton("关闭")
        copy.clicked.connect(lambda: QApplication.clipboard().setText(self.markdown))
        export.clicked.connect(self.export)
        close.clicked.connect(self.accept)
        row.addWidget(copy)
        row.addWidget(export)
        row.addStretch()
        row.addWidget(close)
        layout.addLayout(row)
        self.refresh()
    def refresh(self):
        try:
            self.markdown = self.store.report_markdown(self.store.weekly_report(self.date.date().toPyDate()))
            self.preview.setMarkdown(self.markdown)
        except Exception as exc: QMessageBox.warning(self, "无法生成周报", str(exc))
    def export(self):
        selected = self.date.date().toPyDate()
        monday = selected - timedelta(days=selected.weekday())
        filename, _ = QFileDialog.getSaveFileName(self, "导出周报", f"每周总结-{monday}.md", "Markdown (*.md)")
        if filename:
            try: Path(filename).write_text(self.markdown, encoding="utf-8")
            except OSError as exc: QMessageBox.warning(self, "导出失败", str(exc))
