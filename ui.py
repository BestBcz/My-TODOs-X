"""My-TODOs-X responsive card-style desktop UI."""
import sys
from pathlib import Path
from PyQt5.QtCore import QEvent, QPoint, QRect, QRectF, Qt, QTimer
from PyQt5.QtGui import QColor, QKeySequence, QPainter
from PyQt5.QtWidgets import QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel, QLayout, QLineEdit, QListView, QMainWindow, QMenu, QMessageBox, QPushButton, QScrollArea, QShortcut, QSizePolicy, QSlider, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget
from platform_services import autostart_enabled, set_autostart
from reminders import ReminderService
from settings_service import SettingsService
from task_store import UNCATEGORIZED
from widgets import Card, FlowLayout, TaskDelegate, TaskEditor, TaskListView, TaskModel, WeeklyReportDialog, icon, tool_button
from appearance import DARK, LIGHT, MessageBox as QMessageBox, SiliconDialog, SiliconSwitch, get_text, palette, stylesheet, text_font

class TODOApplication(QMainWindow):
    def __init__(self, store, settings=None, tray_available=None, exit_app=True):
        super().__init__()
        self.store, self.exit_app = store, exit_app
        self.settings = settings or SettingsService(store, self)
        self._exit_requested = self._ready = self._resize_layout_pending = False
        self._closed = False
        self._drag_origin = self._resize_origin = None
        self._frame_padding = 48
        self.category_names = {}
        self.tray_available = QSystemTrayIcon.isSystemTrayAvailable() if tray_available is None else tray_available
        self.setWindowTitle("My-TODOs-X")
        self.setWindowIcon(icon("calendar"))
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(380, 320)
        self.setFont(text_font())
        self.setMouseTracking(True)
        self.settings.error.connect(self.show_error)
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        self.main_layout = layout
        layout.setSizeConstraint(QLayout.SetNoConstraint)
        layout.setContentsMargins(48, 48, 48, 48)
        layout.setSpacing(12)
        self.header = Card()
        self.header.layout_v.setContentsMargins(16, 8, 16, 8)
        row = QHBoxLayout()
        row.setSpacing(6)
        self.logo, self.count_label = QLabel(), QPushButton("没有待办")
        self.logo.setFixedSize(24, 32)
        self.logo.setAlignment(Qt.AlignCenter)
        self.logo.setPixmap(icon("calendar").pixmap(16, 16))
        self.count_label.setObjectName("headerCount")
        self.count_label.setCheckable(True)
        self.count_label.setChecked(True)
        self.count_label.setCursor(Qt.PointingHandCursor)
        self.count_label.setToolTip("收起 / 展开清单")
        self.count_label.clicked.connect(self.toggle_compact)
        self._compact = False
        self._expanded_size = None
        row.addWidget(self.logo)
        row.addWidget(self.count_label)
        row.addStretch()
        self.new_button = tool_button("add", "添加待办 · Ctrl+N", self.toggle_editor_page)
        self.settings_button = tool_button("settings", "设置", self.open_settings)
        self.new_button.setCheckable(True)
        self.settings_button.setCheckable(True)
        self.close_button = tool_button("close", "关闭窗口", self.close)
        for button in (self.new_button, self.settings_button, self.close_button): row.addWidget(button)
        self.header.layout_v.addLayout(row)
        layout.addWidget(self.header)
        self.pages = QStackedWidget()
        self.pages.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        layout.addWidget(self.pages, 1)
        self.build_list_page()
        self.editor = TaskEditor(self)
        self.editor.saved.connect(self.editor_saved)
        self.editor.cancelled.connect(self.cancel_editor)
        self.editor_page = self.scroll_page(self.editor)
        self.pages.addWidget(self.editor_page)
        self.build_settings_page()
        self.build_tray()
        self.pages.currentChanged.connect(self.sync_page_buttons)
        self.settings.changed.connect(self.setting_changed)
        self.reminders = ReminderService(store, self)
        self.reminders.due.connect(self.reminders_due)
        self.reminders.error.connect(self.show_error)
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(120)
        self.search_timer.timeout.connect(self.refresh)
        self.search.textChanged.connect(lambda: self.search_timer.start())
        for combo in (self.status, self.category_filter, self.sort): combo.currentIndexChanged.connect(self.refresh)
        self.resize_idle = QTimer(self)
        self.resize_idle.setSingleShot(True)
        self.resize_idle.setInterval(120)
        self.resize_idle.timeout.connect(self.save_geometry)
        self.settings.set("autostart", autostart_enabled())
        self.sync_settings_controls()
        self.apply_theme()
        self.restore_geometry()
        self.setWindowOpacity(self.settings.get("window_opacity"))
        self.apply_top(self.settings.get("always_on_top"))
        self._ready = True
        self.reload_categories()
        self.refresh()
        QApplication.instance().installEventFilter(self)
        QApplication.instance().screenRemoved.connect(self.restore_geometry)
        for sequence, callback in (("Ctrl+N", self.new_task), ("Ctrl+F", self.focus_search), ("Ctrl+,", self.open_settings)):
            QShortcut(QKeySequence(sequence), self).activated.connect(callback)
        QShortcut(QKeySequence("Delete"), self.list_view).activated.connect(self.delete_selected)
        QShortcut(QKeySequence("Return"), self.list_view).activated.connect(self.edit_selected)
        QTimer.singleShot(0, lambda: self.reminders.start() if not self._closed else None)

    @staticmethod
    def scroll_page(card):
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(card)
        layout.addStretch()
        scroll.setWidget(wrapper)
        return scroll

    def build_list_page(self):
        self.list_page = Card("全部待办")
        self.pages.addWidget(self.list_page)
        self.search = QLineEdit()
        self.search.setObjectName("searchField")
        self.search.setPlaceholderText("搜索事项 · Ctrl+F")
        self.search.setClearButtonEnabled(True)
        self.list_page.layout_v.addWidget(self.search)
        self.search.hide()
        self.search_button = tool_button("search", "搜索事项 · Ctrl+F", self.toggle_search)
        self.search_button.setCheckable(True)
        self.filter_button = tool_button("filter", "分类与排序", self.toggle_filters)
        self.filter_button.setCheckable(True)
        controls = FlowLayout()
        self.status, self.category_filter, self.sort = QComboBox(), QComboBox(), QComboBox()
        for text, value in (("未完成", "active"), ("已完成", "completed"), ("回收站", "trash")): self.status.addItem(text, value)
        for text, value in (("手动排序", "manual"), ("截止时间", "due"), ("优先级", "priority"), ("创建时间", "created")): self.sort.addItem(text, value)
        self.category_filter.setMinimumWidth(105)
        self.category_filter.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.category_filter.setMinimumContentsLength(5)
        for widget in (self.category_filter, self.sort): controls.addWidget(widget)
        self.status.setProperty("compact", True)
        self.status.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.status.setMinimumContentsLength(3)
        self.list_page.header_layout.addWidget(self.status)
        self.list_page.header_layout.addWidget(self.search_button)
        self.list_page.header_layout.addWidget(self.filter_button)
        self.filter_panel = QWidget()
        self.filter_panel.setLayout(controls)
        self.list_page.layout_v.addWidget(self.filter_panel)
        self.filter_panel.hide()
        self.model, self.list_view = TaskModel(self), TaskListView()
        self.list_view.setModel(self.model)
        self.list_view.setMouseTracking(True)
        self.list_view.setFrameShape(QFrame.NoFrame)
        self.list_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.list_view.setResizeMode(QListView.Adjust)
        self.list_view.setDragDropMode(QAbstractItemView.InternalMove)
        self.list_view.setDefaultDropAction(Qt.MoveAction)
        self.list_view.setDropIndicatorShown(True)
        self.list_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.delegate = TaskDelegate(self, self.list_view)
        self.list_view.setItemDelegate(self.delegate)
        self.delegate.toggled.connect(self.toggle_completed)
        self.delegate.menu_requested.connect(self.task_menu)
        self.list_view.doubleClicked.connect(lambda index: self.edit_task(index.data(Qt.UserRole).id))
        self.list_view.customContextMenuRequested.connect(self.list_context_menu)
        self.model.reordered.connect(lambda ids: self.perform(lambda: self.store.reorder(ids)))
        self.list_page.layout_v.addWidget(self.list_view, 1)
        self.empty_label = QLabel("当前没有待办哦")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setObjectName("muted")
        self.empty_label.setWordWrap(True)
        self.list_page.layout_v.addWidget(self.empty_label)
        row = QHBoxLayout()
        weekly = QPushButton("  每周总结")
        weekly.setAccessibleName("每周总结")
        weekly.setObjectName("quietButton")
        weekly.setIcon(icon("weekly"))
        self.weekly_button = weekly
        self.batch_button = tool_button("complete", "全部完成", self.complete_all)
        weekly.clicked.connect(self.open_weekly)
        row.addWidget(weekly)
        row.addStretch()
        row.addWidget(self.batch_button)
        self.list_page.layout_v.addLayout(row)

    def build_settings_page(self):
        card = Card("设置")
        self.settings_controls = {}
        for key, label, description in (
            ("dark_mode", "深色模式", "在深色主题下提供更柔和的视觉体验"),
            ("position_locked", "锁定位置", "保持窗口位置，仍可拖动边缘调整大小"),
            ("always_on_top", "始终在最前", "让待办清单保持在其他窗口前方"),
            ("autostart", "开机自启", "登录 Windows 后自动打开待办清单"),
            ("autostart_hidden", "自启后后台常驻", "启动时收起到托盘，提醒继续工作"),
        ):
            row = QHBoxLayout()
            row.setSpacing(16)
            labels = QVBoxLayout()
            labels.setSpacing(3)
            title, note = QLabel(label), QLabel(description)
            title.setObjectName("settingTitle")
            note.setObjectName("settingDescription")
            note.setWordWrap(True)
            note.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            labels.addWidget(title)
            labels.addWidget(note)
            row.addLayout(labels, 1)
            control = SiliconSwitch()
            control.setAccessibleName(label)
            row.addWidget(control, 0, Qt.AlignVCenter)
            control.toggled.connect(lambda value, name=key: self.change_setting(name, value))
            self.settings_controls[key] = control
            card.layout_v.addLayout(row)
            card.layout_v.addSpacing(8)
        self.settings_controls["autostart"].setEnabled(sys.platform == "win32")
        row = QHBoxLayout()
        opacity_title = QLabel("窗口不透明度")
        opacity_title.setObjectName("settingTitle")
        row.addWidget(opacity_title)
        self.opacity_label = QLabel("100%")
        row.addStretch()
        row.addWidget(self.opacity_label)
        card.layout_v.addLayout(row)
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(30, 100)
        self.opacity_slider.setSingleStep(1)
        self.opacity_slider.valueChanged.connect(lambda value: self.settings.set("window_opacity", value/100, deferred=True))
        self.opacity_slider.sliderReleased.connect(self.settings.flush)
        card.layout_v.addWidget(self.opacity_slider)
        label = QLabel("数值越低越透明，背景、文字和按钮会一起变淡")
        label.setWordWrap(True)
        label.setObjectName("muted")
        card.layout_v.addWidget(label)
        row = QHBoxLayout()
        row.addWidget(QLabel("关闭窗口时"))
        self.close_behavior = QComboBox()
        for label, value in (("每次询问", "ask"), ("后台常驻", "tray"), ("退出程序", "quit")): self.close_behavior.addItem(label, value)
        self.close_behavior.currentIndexChanged.connect(lambda: self.change_setting("close_behavior", self.close_behavior.currentData()))
        row.addWidget(self.close_behavior, 1)
        card.layout_v.addLayout(row)
        for text, callback in (("管理分类", self.manage_categories), ("导入旧版 todos.ini", self.import_legacy)):
            button = QPushButton(text)
            button.clicked.connect(callback)
            card.layout_v.addWidget(button)
        data_label = QLabel("事项与设置自动保存，更新软件后仍会保留")
        data_label.setWordWrap(True)
        data_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        data_label.setObjectName("muted")
        data_label.setToolTip(str(self.store.path.parent))
        card.layout_v.addWidget(data_label)
        about = QLabel("My-TODOs-X · 基于霏泠 Ice 的 My-TODOs\nGPL v3 · 本地保存，无需账号")
        about.setWordWrap(True)
        about.setObjectName("muted")
        card.layout_v.addWidget(about)
        row = QHBoxLayout()
        back, quit_button = QPushButton("返回清单"), QPushButton("退出程序")
        back.clicked.connect(self.show_list)
        quit_button.clicked.connect(self.request_exit)
        row.addWidget(back)
        row.addStretch()
        row.addWidget(quit_button)
        card.layout_v.addLayout(row)
        self.settings_page = self.scroll_page(card)
        self.pages.addWidget(self.settings_page)

    def build_tray(self):
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip("My-TODOs-X")
        self.tray_menu = QMenu(self)
        for text, callback in (("显示窗口", self.restore_window), ("隐藏窗口", self.hide_to_tray), ("添加待办", self.new_task)):
            self.tray_menu.addAction(text, callback)
        self.top_action = self.tray_menu.addAction("窗口始终在最前")
        self.top_action.setCheckable(True)
        self.top_action.toggled.connect(lambda value: self.change_setting("always_on_top", value))
        self.tray_menu.addAction("每周总结", self.open_weekly)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction("退出程序", self.request_exit)
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(lambda reason: self.restore_window() if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick) else None)
        self.tray.messageClicked.connect(self.restore_window)
        if self.tray_available: self.tray.show()

    def sync_settings_controls(self):
        for key, control in self.settings_controls.items():
            control.blockSignals(True)
            control.setChecked(self.settings.get(key))
            control.blockSignals(False)
        self.settings_controls["autostart_hidden"].setEnabled(self.settings.get("autostart") and self.tray_available)
        self.opacity_slider.blockSignals(True)
        value = round(self.settings.get("window_opacity")*100)
        self.opacity_slider.setValue(value)
        self.opacity_slider.blockSignals(False)
        self.opacity_label.setText(f"{value}%")
        self.close_behavior.blockSignals(True)
        self.close_behavior.setCurrentIndex(self.close_behavior.findData(self.settings.get("close_behavior")))
        self.close_behavior.blockSignals(False)
        self.top_action.blockSignals(True)
        self.top_action.setChecked(self.settings.get("always_on_top"))
        self.top_action.blockSignals(False)

    def change_setting(self, key, value):
        if key == "autostart":
            try:
                previous = autostart_enabled()
                set_autostart(value)
                if not self.settings.set(key, value): set_autostart(previous)
            except Exception as exc: self.show_error(f"无法修改自启：{exc}")
            self.sync_settings_controls()
        elif not self.settings.set(key, value): self.sync_settings_controls()

    def setting_changed(self, key, value):
        if key in ("window_x", "window_y", "window_width", "window_height"): return
        if key == "dark_mode": self.apply_theme()
        elif key == "window_opacity": self.setWindowOpacity(value)
        elif key == "always_on_top": self.apply_top(value)
        self.sync_settings_controls()

    def apply_top(self, enabled):
        visible, geometry, state = self.isVisible(), self.geometry(), self.windowState()
        self.setWindowFlag(Qt.WindowStaysOnTopHint, enabled)
        self.setGeometry(geometry)
        self.setWindowOpacity(self.settings.get("window_opacity"))
        if visible:
            self.show()
            self.setWindowState(state)

    def apply_theme(self):
        dark = self.settings.get("dark_mode")
        self.setProperty("darkTheme", dark)
        self.setStyleSheet(stylesheet(dark))
        c = DARK if dark else LIGHT
        self.logo.setPixmap(icon("calendar", c["icon"]).pixmap(16, 16))
        self.weekly_button.setIcon(icon("weekly", c["icon"]))
        for widget in self.findChildren(QWidget): widget.update()
        if hasattr(self, "delegate"):
            self.delegate.cache.clear()
            self.list_view.doItemsLayout()
            self.list_view.viewport().update()
        self.update()

    def restore_geometry(self):
        width, height = self.settings.get("window_width"), self.settings.get("window_height")
        x, y = self.settings.get("window_x"), self.settings.get("window_y")
        screen = QApplication.primaryScreen().availableGeometry()
        rect = QRect(x if x is not None else screen.center().x()-width//2,
                     y if y is not None else screen.center().y()-height//2, width, height)
        screens = [s.availableGeometry() for s in QApplication.screens()]
        best = max(screens, key=lambda s: max(0, s.intersected(rect).width()) * max(0, s.intersected(rect).height()))
        if not best.intersects(rect): best = screen
        rect.setSize(rect.size().boundedTo(best.size()).expandedTo(self.minimumSize()))
        rect.moveLeft(max(best.left(), min(rect.left(), best.right()-rect.width()+1)))
        rect.moveTop(max(best.top(), min(rect.top(), best.bottom()-rect.height()+1)))
        self.setGeometry(rect)

    def save_geometry(self):
        if self._ready and not self.isMinimized() and not self.isMaximized():
            size = self._expanded_size if self._compact and self._expanded_size else self.size()
            self.settings.set_many({"window_x": self.x(), "window_y": self.y(),
                                    "window_width": self.width(), "window_height": size.height()}, deferred=True)

    def update_frame_padding(self):
        padding = max(16, min(48, 16 + (self.width()-380)*32//120))
        if padding != self._frame_padding:
            self._frame_padding = padding
            self.main_layout.setContentsMargins(padding, padding, padding, padding)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        # Keep transparent resize margins hit-testable on Windows layered windows.
        painter.fillRect(self.rect(), QColor(0,0,0,1))
        surfaces = [self.header]
        if self.pages.isVisible():
            current = self.pages.currentWidget()
            surfaces.append(current if isinstance(current, Card) else current.widget().findChild(Card))
        for surface in surfaces:
            if surface is None: continue
            origin = surface.mapTo(self, QPoint(0,0))
            rect = QRectF(origin.x(), origin.y(), surface.width(), surface.height())
            for spread in range(22, 0, -2):
                painter.setBrush(QColor(0, 0, 0, 2 if spread > 10 else 3))
                painter.drawRoundedRect(rect.adjusted(-spread,-spread,spread,spread), 8+spread, 8+spread)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._ready: return
        self.update_frame_padding()
        self.save_geometry()
        self.resize_idle.start()
        if not self._resize_layout_pending:
            self._resize_layout_pending = True
            QTimer.singleShot(0, self.layout_resized_items)

    def layout_resized_items(self):
        self._resize_layout_pending = False
        self.list_view.doItemsLayout()

    def moveEvent(self, event):
        super().moveEvent(event)
        if self._ready: self.save_geometry()

    def edges_at(self, point):
        edges = Qt.Edges()
        margin = self._frame_padding + 2
        if point.x() < margin: edges |= Qt.LeftEdge
        elif point.x() >= self.width()-margin: edges |= Qt.RightEdge
        if point.y() < margin: edges |= Qt.TopEdge
        elif point.y() >= self.height()-margin: edges |= Qt.BottomEdge
        return edges

    def eventFilter(self, obj, event):
        if not self._ready or not isinstance(obj, QWidget) or not (obj is self or self.isAncestorOf(obj)) or obj.window() is not self:
            return False
        kind = event.type()
        if kind in (QEvent.MouseMove, QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
            point = self.mapFromGlobal(event.globalPos())
            edges = self.edges_at(point)
            if kind == QEvent.MouseMove:
                if self._resize_origin:
                    origin, geometry, resize_edges = self._resize_origin
                    delta, rect = event.globalPos()-origin, QRect(geometry)
                    if resize_edges & Qt.LeftEdge: rect.setLeft(min(geometry.right()-self.minimumWidth()+1, geometry.left()+delta.x()))
                    if resize_edges & Qt.RightEdge: rect.setRight(max(geometry.left()+self.minimumWidth()-1, geometry.right()+delta.x()))
                    if resize_edges & Qt.TopEdge: rect.setTop(min(geometry.bottom()-self.minimumHeight()+1, geometry.top()+delta.y()))
                    if resize_edges & Qt.BottomEdge: rect.setBottom(max(geometry.top()+self.minimumHeight()-1, geometry.bottom()+delta.y()))
                    self.setGeometry(rect)
                    return True
                if self._drag_origin:
                    origin, position = self._drag_origin
                    self.move(position + event.globalPos()-origin)
                    return True
                if edges in (Qt.LeftEdge | Qt.TopEdge, Qt.RightEdge | Qt.BottomEdge): cursor = Qt.SizeFDiagCursor
                elif edges in (Qt.RightEdge | Qt.TopEdge, Qt.LeftEdge | Qt.BottomEdge): cursor = Qt.SizeBDiagCursor
                elif edges & (Qt.LeftEdge | Qt.RightEdge): cursor = Qt.SizeHorCursor
                elif edges: cursor = Qt.SizeVerCursor
                else: cursor = Qt.ArrowCursor
                if edges: self.setCursor(cursor)
                else: self.unsetCursor()
            elif kind == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                if edges and not self.isMaximized():
                    outer_edge = point.x() < 12 or point.x() >= self.width()-12 or point.y() < 12 or point.y() >= self.height()-12
                    if not outer_edge or not self.windowHandle() or not self.windowHandle().startSystemResize(edges):
                        self._resize_origin = (event.globalPos(), self.geometry(), edges)
                        self.grabMouse()
                    return True
                if obj in (self.header, self.logo) and not self.settings.get("position_locked"):
                    if not self.windowHandle() or not self.windowHandle().startSystemMove():
                        self._drag_origin = (event.globalPos(), self.pos())
                        self.grabMouse()
                    return True
            elif kind == QEvent.MouseButtonRelease:
                if self._resize_origin or self._drag_origin:
                    self._resize_origin = self._drag_origin = None
                    self.releaseMouse()
                    self.save_geometry()
                    return True
        return super().eventFilter(obj, event)

    def show_error(self, message):
        QMessageBox.warning(self, "操作未完成", str(message))

    def perform(self, operation):
        try: operation()
        except Exception as exc:
            self.show_error(str(exc))
            return False
        self.refresh()
        return True

    def reload_categories(self):
        self.category_names = dict(self.store.categories())
        selected = self.category_filter.currentData()
        self.category_filter.blockSignals(True)
        self.category_filter.clear()
        self.category_filter.addItem("全部分类", None)
        for key, name in self.category_names.items(): self.category_filter.addItem(name, key)
        self.category_filter.setCurrentIndex(max(0, self.category_filter.findData(selected)))
        self.category_filter.blockSignals(False)
        self.editor.reload_categories()

    def refresh(self):
        status, category, sort, search = self.status.currentData(), self.category_filter.currentData(), self.sort.currentData(), self.search.text()
        tasks = self.store.query(status, search, category, sort)
        selected = self.list_view.currentIndex().data(Qt.UserRole)
        position = self.list_view.verticalScrollBar().value()
        self.model.set_tasks(tasks, status == "active" and sort == "manual" and not search and category is None)
        self.delegate.cache.clear()
        self.list_view.setDragEnabled(self.model.can_reorder)
        self.list_view.setAcceptDrops(self.model.can_reorder)
        if selected:
            for row, task in enumerate(tasks):
                if task.id == selected.id: self.list_view.setCurrentIndex(self.model.index(row, 0))
        self.list_view.verticalScrollBar().setValue(position)
        amount = len(self.store.query())
        self.count_label.setText(f"{amount}个待办事项" if amount else "没有待办")
        self.tray.setToolTip(f"My-TODOs-X · {amount} 个待办")
        self.empty_label.setVisible(not tasks)
        self.empty_label.setText("没有匹配的事项" if search or category else {"active": "当前没有待办哦", "completed": "还没有完成记录", "trash": "回收站是空的"}[status])
        self.batch_button.setToolTip("清空回收站" if status == "trash" else "全部完成")
        self.batch_button.setAccessibleName(self.batch_button.toolTip())
        self.batch_button.setVisible(status != "completed")
        self.batch_button.setEnabled(bool(tasks))

    def show_list(self):
        self.ensure_expanded()
        self.pages.setCurrentWidget(self.list_page)
        self.refresh()

    def ensure_expanded(self):
        if self._compact:
            self.count_label.setChecked(True)
            self.toggle_compact(True)

    def toggle_compact(self, expanded):
        if expanded:
            self._compact = False
            self.setMinimumHeight(320)
            self.pages.show()
            if self._expanded_size: self.resize(self._expanded_size)
        else:
            self._expanded_size = self.size()
            self._compact = True
            self.pages.hide()
            self.setMinimumHeight(48+2*self._frame_padding)
            self.resize(self.width(), 48+2*self._frame_padding)
        self.update()

    def toggle_search(self, checked):
        self.search.setVisible(checked)
        if checked: self.search.setFocus()
        else: self.search.clear()

    def toggle_filters(self, checked):
        self.filter_panel.setVisible(checked)

    def focus_search(self):
        self.show_list()
        self.search_button.setChecked(True)
        self.search.show()
        self.search.setFocus()

    def confirm_unsaved(self):
        if not self.editor.dirty(): return True
        choice = QMessageBox.question(self, "未保存的修改", "是否保存当前事项？", QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
        if choice == QMessageBox.Cancel: return False
        if choice == QMessageBox.Save: return self.editor.save()
        self.editor.baseline = None
        return True

    def new_task(self):
        if not self.confirm_unsaved(): return
        self.restore_window()
        self.pages.setCurrentWidget(self.editor_page)
        self.editor.open()

    def edit_task(self, task_id):
        task = self.store.get(task_id)
        if task.trashed:
            self.show_error("请先从回收站恢复事项。")
            return
        if not self.confirm_unsaved(): return
        self.pages.setCurrentWidget(self.editor_page)
        self.editor.open(task)

    def editor_saved(self):
        self.show_list()
        self.reminders.check()

    def cancel_editor(self):
        if self.editor.dirty() and QMessageBox.question(self, "取消修改", "放弃尚未保存的修改？") != QMessageBox.Yes: return
        self.editor.baseline = None
        self.show_list()

    def open_settings(self):
        self.ensure_expanded()
        self.pages.setCurrentWidget(self.list_page if self.pages.currentWidget() is self.settings_page else self.settings_page)

    def toggle_editor_page(self):
        if self.pages.currentWidget() is self.editor_page: self.cancel_editor()
        else: self.new_task()
        self.sync_page_buttons()

    def sync_page_buttons(self):
        self.new_button.setChecked(self.pages.currentWidget() is self.editor_page)
        self.settings_button.setChecked(self.pages.currentWidget() is self.settings_page)

    def toggle_completed(self, task_id):
        task = self.store.get(task_id)
        self.perform(lambda: self.store.reopen(task_id) if task.status == "completed" else self.store.complete(task_id))

    def list_context_menu(self, point):
        index = self.list_view.indexAt(point)
        if index.isValid(): self.task_menu(index.data(Qt.UserRole).id, self.list_view.viewport().mapToGlobal(point))

    def task_menu(self, task_id, point):
        task, menu = self.store.get(task_id), QMenu(self)
        if task.trashed:
            menu.addAction("从回收站恢复", lambda: self.perform(lambda: self.store.restore(task_id)))
            menu.addAction("永久删除…", lambda: self.permanent_delete([task_id]))
        else:
            menu.addAction("修改事项", lambda: self.edit_task(task_id))
            menu.addAction("恢复为待办" if task.status == "completed" else "标记完成", lambda: self.toggle_completed(task_id))
            menu.addAction("取消事项置顶" if task.pinned else "事项置顶", lambda: self.perform(lambda: self.store.update(task_id, pinned=not task.pinned)))
            menu.addSeparator()
            menu.addAction("移入回收站", lambda: self.perform(lambda: self.store.trash(task_id)))
        menu.exec_(point)

    def edit_selected(self):
        task = self.list_view.currentIndex().data(Qt.UserRole)
        if task: self.edit_task(task.id)

    def delete_selected(self):
        task = self.list_view.currentIndex().data(Qt.UserRole)
        if task:
            if task.trashed: self.permanent_delete([task.id])
            else: self.perform(lambda: self.store.trash(task.id))

    def permanent_delete(self, ids):
        if QMessageBox.question(self, "永久删除", f"永久删除 {len(ids)} 项？事项无法恢复，已经发生的周报记录会保留。") != QMessageBox.Yes: return
        self.perform(lambda: self.store.delete_many(ids))

    def complete_all(self):
        ids = [task.id for task in self.model.tasks]
        if self.status.currentData() == "trash": self.permanent_delete(ids)
        elif QMessageBox.question(self, "全部完成", f"将当前显示的 {len(ids)} 项标记完成？") == QMessageBox.Yes:
            self.perform(lambda: self.store.complete_many(ids))

    def add_category(self):
        name, accepted = get_text(self, "新建分类", "分类名称")
        if accepted:
            try: category_id = self.store.add_category(name)
            except Exception as exc:
                self.show_error(str(exc))
                return
            self.reload_categories()
            self.editor.category.setCurrentIndex(self.editor.category.findData(category_id))
            self.refresh()

    def manage_categories(self):
        dialog = SiliconDialog("管理分类", self)
        dialog.setMinimumWidth(320)
        layout, combo = dialog.body, QComboBox()
        for key, name in self.store.categories(): combo.addItem(name, key)
        layout.addWidget(combo)
        row = QHBoxLayout()
        add, rename, delete = QPushButton("新建"), QPushButton("重命名"), QPushButton("删除")
        for button in (add, rename, delete): row.addWidget(button)
        layout.addLayout(row)
        def reload():
            current = combo.currentData()
            combo.clear()
            for key, name in self.store.categories(): combo.addItem(name, key)
            combo.setCurrentIndex(max(0, combo.findData(current)))
            self.reload_categories()
            self.refresh()
        def create():
            self.add_category()
            reload()
        def change_name():
            if combo.currentData() == UNCATEGORIZED: return
            name, accepted = get_text(dialog, "重命名分类", "分类名称", text=combo.currentText())
            if accepted and self.perform(lambda: self.store.rename_category(combo.currentData(), name)): reload()
        def remove():
            if combo.currentData() == UNCATEGORIZED: return
            if QMessageBox.question(dialog, "删除分类", "此分类中的事项将移到“未分类”，继续？") == QMessageBox.Yes:
                if self.perform(lambda: self.store.delete_category(combo.currentData())): reload()
        add.clicked.connect(create)
        rename.clicked.connect(change_name)
        delete.clicked.connect(remove)
        def enable():
            rename.setEnabled(combo.currentData() != UNCATEGORIZED)
            delete.setEnabled(combo.currentData() != UNCATEGORIZED)
        combo.currentIndexChanged.connect(enable)
        enable()
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec_()

    def import_legacy(self):
        filename, _ = QFileDialog.getOpenFileName(self, "导入旧版事项", "", "旧版事项 (todos.ini);;INI (*.ini)")
        if filename:
            try: amount = self.store.import_legacy(filename)
            except Exception as exc:
                self.show_error(f"导入失败：{exc}")
                return
            self.refresh()
            QMessageBox.information(self, "导入完成", f"已导入 {amount} 项，原文件保持不变。")

    def open_weekly(self):
        self.restore_window()
        WeeklyReportDialog(self.store, self).exec_()

    def reminders_due(self, tasks):
        self.refresh()
        if self.tray_available and QSystemTrayIcon.supportsMessages():
            text = tasks[0].text if len(tasks) == 1 else f"有 {len(tasks)} 项提醒已到时间：\n" + "\n".join(t.text.splitlines()[0] for t in tasks[:3])
            self.tray.showMessage("My-TODOs-X · 待办提醒", text[:240], QSystemTrayIcon.Information)
        else: self.show_error(f"有 {len(tasks)} 项提醒已到时间：\n" + "\n".join(t.text for t in tasks[:5]))

    def restore_window(self):
        self.ensure_expanded()
        self.restore_geometry()
        self.setWindowOpacity(self.settings.get("window_opacity"))
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def hide_to_tray(self):
        if self.tray_available:
            self.save_geometry()
            self.settings.flush()
            self.hide()

    def close_choice(self):
        dialog = SiliconDialog("关闭 My-TODOs-X", self)
        layout = dialog.body
        label = QLabel("后台常驻可以继续发送事项提醒。请选择关闭方式：")
        label.setWordWrap(True)
        layout.addWidget(label)
        remember = QCheckBox("记住选择，以后可在设置中修改")
        remember.setChecked(True)
        layout.addWidget(remember)
        row = QHBoxLayout()
        tray, quit_button, cancel = QPushButton("后台常驻"), QPushButton("退出程序"), QPushButton("取消")
        tray.setEnabled(self.tray_available)
        choice = [None]
        def choose(value):
            choice[0] = value
            dialog.accept()
        tray.clicked.connect(lambda: choose("tray"))
        quit_button.clicked.connect(lambda: choose("quit"))
        cancel.clicked.connect(dialog.reject)
        for button in (tray, quit_button, cancel): row.addWidget(button)
        layout.addLayout(row)
        if dialog.exec_() != QDialog.Accepted: return None
        if remember.isChecked() and not self.settings.set("close_behavior", choice[0]): return None
        return choice[0]

    def request_exit(self):
        if not self.confirm_unsaved(): return
        self._exit_requested = True
        self.close()

    def stop_services(self):
        self.reminders.stop()
        self.search_timer.stop()
        self.resize_idle.stop()
        self.settings.timer.stop()
        self.tray.hide()
        QApplication.instance().removeEventFilter(self)
        try: QApplication.instance().screenRemoved.disconnect(self.restore_geometry)
        except TypeError: pass

    def closeEvent(self, event):
        if self._closed:
            event.accept()
            return
        behavior = "quit" if self._exit_requested else self.settings.get("close_behavior")
        if behavior == "ask": behavior = self.close_choice()
        if behavior is None:
            event.ignore()
            return
        if behavior == "tray" and self.tray_available:
            self.hide_to_tray()
            event.ignore()
            return
        if not self._exit_requested and not self.confirm_unsaved():
            event.ignore()
            return
        self.save_geometry()
        if not self.settings.flush():
            self._exit_requested = False
            event.ignore()
            return
        self.stop_services()
        self._closed = True
        event.accept()
        if self.exit_app: QApplication.instance().quit()
