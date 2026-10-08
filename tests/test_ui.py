from datetime import datetime, timedelta, timezone
from time import perf_counter
import pytest
from PyQt5.QtCore import QEvent, QModelIndex, QPoint, QPointF, Qt
from PyQt5.QtGui import QDropEvent, QMouseEvent
from PyQt5.QtWidgets import QMessageBox, QWidget
from reminders import ReminderService
from settings_service import SettingsService
from task_store import TaskStore
from ui import TODOApplication

@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr("ui.autostart_enabled", lambda: False)
    store = TaskStore(tmp_path / "mytodos.sqlite3")
    store.save_settings({"close_behavior": "quit"})
    window = TODOApplication(store, tray_available=False, exit_app=False)
    window.errors = []
    monkeypatch.setattr(window, "show_error", window.errors.append)
    window.show()
    qtbot.wait(20)
    yield window
    window.editor.baseline = None
    window.settings.set("close_behavior", "quit")
    window.close()
    store.close()

def test_create_edit_multiline_complete_restore(window, qtbot):
    window.new_task()
    window.editor.text.setPlainText("第一行\n第二行")
    assert window.editor.save()
    task = window.store.query()[0]
    window.edit_task(task.id)
    window.editor.text.setPlainText("修改后的事项")
    assert window.editor.save()
    assert window.store.get(task.id).text == "修改后的事项"
    window.toggle_completed(task.id)
    assert not window.store.query()
    window.status.setCurrentIndex(window.status.findData("completed"))
    assert window.model.rowCount() == 1
    window.toggle_completed(task.id)
    assert len(window.store.query()) == 1

def test_failed_editor_save_preserves_input(window, monkeypatch):
    window.new_task()
    window.editor.text.setPlainText("不能丢失的输入")
    monkeypatch.setattr(window.store, "add", lambda **kw: (_ for _ in ()).throw(OSError("disk full")))
    assert not window.editor.save()
    assert window.editor.text.toPlainText() == "不能丢失的输入"
    assert window.editor.dirty()
    assert "disk full" in window.errors[-1]

def test_edit_elapsed_reminder_preserves_precision_and_sent_state(window):
    past = datetime.now(timezone.utc)-timedelta(days=1)
    task = window.store.add("已提醒的事项", remind_at=past)
    window.store.mark_reminders_sent([task.id])
    window.edit_task(task.id)
    window.editor.text.setPlainText("只修改内容")
    assert window.editor.save()
    saved = window.store.get(task.id)
    assert saved.remind_at == task.remind_at and saved.reminder_sent_at

def test_mouse_resize_fallback_and_position_lock(window, monkeypatch):
    handle = window.windowHandle()
    monkeypatch.setattr(handle, "startSystemResize", lambda edges: False)
    window.resize(500, 640)
    window.settings.set("position_locked", True)
    origin = QPoint(window.width()-2, window.height()-2)
    global_origin = window.mapToGlobal(origin)
    press = QMouseEvent(QEvent.MouseButtonPress, QPointF(origin), QPointF(global_origin), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    assert window.eventFilter(window, press)
    target = origin+QPoint(70,40)
    move = QMouseEvent(QEvent.MouseMove, QPointF(target), QPointF(global_origin+QPoint(70,40)), Qt.NoButton, Qt.LeftButton, Qt.NoModifier)
    assert window.eventFilter(window, move)
    assert window.width() == 570 and window.height() == 680
    release = QMouseEvent(QEvent.MouseButtonRelease, QPointF(target), QPointF(global_origin+QPoint(70,40)), Qt.LeftButton, Qt.NoButton, Qt.NoModifier)
    assert window.eventFilter(window, release)
    assert window._resize_origin is None

def test_resize_cursor_clears_when_entering_content(window):
    edge, content = QPoint(1,1), QPoint(80,120)
    for target, point in ((window.centralWidget(), edge), (window.count_label, content)):
        event = QMouseEvent(QEvent.MouseMove, QPointF(point), QPointF(window.mapToGlobal(point)), Qt.NoButton, Qt.NoButton, Qt.NoModifier)
        window.eventFilter(target, event)
        assert window.cursor().shape() == (Qt.SizeFDiagCursor if point == edge else Qt.ArrowCursor)

def test_opacity_top_geometry_and_hidden_state(window, qtbot):
    window.resize(680, 520)
    qtbot.wait(30)
    geometry = window.geometry()
    window.opacity_slider.setValue(65)
    assert window.windowOpacity() == pytest.approx(.65, abs=.004)
    window.settings.set("always_on_top", True)
    assert window.windowFlags() & Qt.WindowStaysOnTopHint
    assert window.geometry() == geometry
    assert window.top_action.isChecked()
    assert window.settings_controls["always_on_top"].isChecked()
    window.hide()
    window.top_action.setChecked(False)
    assert not window.isVisible()
    assert not window.windowFlags() & Qt.WindowStaysOnTopHint
    assert window.windowOpacity() == pytest.approx(.65, abs=.004)
    window.settings.flush()
    assert window.store.settings()["window_opacity"] == .65

def test_geometry_and_settings_restore(window, qtbot):
    window.resize(640, 480)
    window.settings.set("always_on_top", True)
    window.opacity_slider.setValue(42)
    qtbot.wait(400)
    other = TODOApplication(window.store, tray_available=False, exit_app=False)
    qtbot.addWidget(other)
    assert other.width() == 640 and other.height() == 480
    assert other.windowFlags() & Qt.WindowStaysOnTopHint
    assert other.windowOpacity() == pytest.approx(.42, abs=.004)
    other.close()

def test_settings_failure_does_not_commit(window, monkeypatch):
    def fail(*args): raise OSError("permission denied")
    monkeypatch.setattr(window.settings.store, "save_settings", fail)
    errors = []
    window.settings.error.disconnect()
    window.settings.error.connect(errors.append)
    assert not window.settings.set("always_on_top", True)
    assert not window.settings.get("always_on_top")
    window.settings.set("window_opacity", .6, deferred=True)
    assert not window.settings.flush()
    assert window.settings.pending["window_opacity"] == .6
    assert errors
    window.settings.pending.clear()

def test_resize_wrap_and_500_rows_without_recreating_widgets(window, qtbot):
    for index in range(500): window.store.add(f"事项 {index}：连续拖拽缩放时文字应该自然换行。" * 3)
    window.refresh()
    widgets = len(window.findChildren(QWidget))
    assert window.model.rowCount() == 500
    window.resize(900, 700)
    qtbot.wait(20)
    wide = window.list_view.visualRect(window.model.index(0, 0)).height()
    frames = []
    for width in range(860, 379, -40):
        begin = perf_counter()
        window.resize(width, 500)
        QApplication = __import__("PyQt5.QtWidgets", fromlist=["QApplication"]).QApplication
        QApplication.processEvents()
        frames.append(perf_counter()-begin)
    qtbot.wait(20)
    narrow = window.list_view.visualRect(window.model.index(0, 0)).height()
    assert narrow > wide
    assert len(window.findChildren(QWidget)) == widgets
    assert window.width() >= 380 and window.height() >= 320
    assert max(frames) < .25
    geometry = window.geometry()
    window.open_settings()
    window.new_task()
    assert window.geometry() == geometry

@pytest.mark.parametrize("point,expected", [
    ((0,100), Qt.LeftEdge), ((499,100), Qt.RightEdge), ((100,0), Qt.TopEdge), ((100,639), Qt.BottomEdge),
    ((0,0), Qt.LeftEdge|Qt.TopEdge), ((499,0), Qt.RightEdge|Qt.TopEdge),
    ((0,639), Qt.LeftEdge|Qt.BottomEdge), ((499,639), Qt.RightEdge|Qt.BottomEdge),
])
def test_all_resize_edges(window, point, expected):
    window.resize(500,640)
    assert window.edges_at(QPoint(*point)) == expected

def test_drag_and_filter_guard(window, qtbot):
    first, second = window.store.add("first"), window.store.add("second")
    window.refresh()
    mime = window.model.mimeData([window.model.index(0,0)])
    window.model.dropMimeData(mime, Qt.MoveAction, 2, 0, QModelIndex())
    assert [t.id for t in window.store.query()] == [second.id, first.id]
    window.search.setText("first")
    qtbot.wait(150)
    assert window.model.rowCount() == 1 and not window.model.can_reorder

def test_drag_drop_accepts_move_without_deleting_source(window, qtbot):
    first, second = window.store.add("first"), window.store.add("second")
    window.refresh()
    qtbot.wait(20)
    mime = window.model.mimeData([window.model.index(0,0)])
    target = window.list_view.visualRect(window.model.index(1,0)).bottomLeft()
    event = QDropEvent(QPointF(target), Qt.MoveAction, mime, Qt.LeftButton, Qt.NoModifier)
    window.list_view.dropEvent(event)
    assert event.isAccepted()
    assert [t.id for t in window.store.query()] == [second.id, first.id]
    assert window.model.rowCount() == 2

def test_closed_window_does_not_restart_queued_reminder(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr("ui.autostart_enabled", lambda: False)
    store = TaskStore(tmp_path / "queued.sqlite3")
    store.save_settings({"close_behavior": "quit"})
    window = TODOApplication(store, tray_available=False, exit_app=False)
    window.close()
    qtbot.wait(20)
    assert not window.reminders.timer.isActive()
    store.close()

def test_tray_close_and_explicit_exit(window, monkeypatch):
    window.tray_available = True
    window.settings.set("close_behavior", "tray")
    window.close()
    assert not window.isVisible()
    assert window.reminders.timer.isActive()
    window.restore_window()
    assert window.isVisible()
    window.request_exit()
    assert not window.reminders.timer.isActive()

def test_close_ask_can_cancel_and_select_tray(window, monkeypatch):
    window.settings.set("close_behavior", "ask")
    monkeypatch.setattr(window, "close_choice", lambda: None)
    window.close()
    assert window.isVisible()
    window.tray_available = True
    monkeypatch.setattr(window, "close_choice", lambda: "tray")
    window.close()
    assert not window.isVisible()

def test_catchup_reminders_group_and_deduplicate(qtbot, tmp_path):
    store = TaskStore(tmp_path / "reminders.sqlite3")
    now = datetime.now(timezone.utc)
    store.add("one", remind_at=now-timedelta(hours=1))
    store.add("two", remind_at=now-timedelta(hours=2))
    service = ReminderService(store)
    groups = []
    service.due.connect(groups.append)
    service.check()
    service.check()
    assert len(groups) == 1 and len(groups[0]) == 2
    service.stop()
    store.close()
