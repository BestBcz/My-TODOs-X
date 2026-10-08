from datetime import date, datetime, timedelta, timezone
import sqlite3
import pytest
from task_store import TaskStore, UNCATEGORIZED, stamp

ZONE = timezone(timedelta(hours=8))

@pytest.fixture
def store(tmp_path):
    store = TaskStore(tmp_path / "mytodos.sqlite3")
    yield store
    store.close()

def test_duplicate_multiline_tasks_edit_and_reload(store):
    first = store.add("重复事项\n第二行")
    second = store.add(first.text)
    store.update(first.id, text="修改后的事项\n第二行", priority=2, pinned=True)
    another = TaskStore(store.path)
    assert another.get(second.id).text == "重复事项\n第二行"
    assert another.get(first.id).priority == 2
    another.close()

def test_complete_restore_trash_and_delete(store):
    task = store.add("事项")
    store.complete(task.id)
    store.complete(task.id)
    assert len(store.query("completed")) == 1
    store.trash(task.id)
    assert not store.query("completed")
    assert len(store.query("trash")) == 1
    store.restore(task.id)
    assert store.get(task.id).status == "completed"
    store.reopen(task.id)
    with pytest.raises(ValueError): store.delete(task.id)
    store.trash(task.id)
    store.delete(task.id)
    assert not store.query("trash")

def test_sort_filter_category_and_drag_order(store):
    category = store.add_category("工作")
    a = store.add("Alpha", priority=0)
    b = store.add("Beta", category_id=category, priority=2)
    c = store.add("Alpha pinned", pinned=True)
    assert [t.id for t in store.query(sort="priority")] == [c.id, b.id, a.id]
    assert [t.id for t in store.query(search="ALPHA")] == [c.id, a.id]
    store.reorder([c.id, b.id, a.id])
    assert [t.id for t in store.query()] == [c.id, b.id, a.id]
    with pytest.raises(ValueError): store.reorder([a.id, c.id, b.id])
    with pytest.raises(ValueError): store.reorder([c.id, b.id])
    store.delete_category(category)
    assert store.get(b.id).category_id == UNCATEGORIZED

def test_failed_save_is_transactional(store, monkeypatch):
    task = store.add("保留原内容")
    def fail(*args): raise sqlite3.OperationalError("disk full")
    monkeypatch.setattr(store, "_event", fail)
    with pytest.raises(sqlite3.OperationalError): store.update(task.id, text="未成功保存")
    assert store.get(task.id).text == "保留原内容"

def test_batch_operations_rollback_on_partial_failure(store):
    first, second = store.add("first"), store.add("second")
    with pytest.raises(ValueError): store.complete_many([first.id, "missing"])
    assert store.get(first.id).status == "active"
    store.trash(first.id)
    with pytest.raises(ValueError): store.delete_many([first.id, second.id])
    assert store.get(first.id).trashed

def test_legacy_migration_backup_idempotent_and_retry(tmp_path, monkeypatch):
    legacy = tmp_path / "old app"
    legacy.mkdir()
    original = "<TODO-START-MARK>一样\n第二行<TODO-START-MARK>一样\n第二行"
    (legacy / "todos.ini").write_text(original, encoding="utf-8")
    (legacy / "options.ini").write_text("USE_DARK_MODE = True\nFIXED_POSITION_X = -200\nFIXED_POSITION_Y = bad", encoding="utf-8")
    store = TaskStore(tmp_path / "new" / "mytodos.sqlite3")
    event = store._event
    monkeypatch.setattr(store, "_event", lambda *a: (_ for _ in ()).throw(OSError("failed")))
    with pytest.raises(OSError): store.migrate_legacy(legacy)
    assert not store.query()
    monkeypatch.setattr(store, "_event", event)
    assert store.migrate_legacy(legacy) == 2
    assert store.migrate_legacy(legacy) == 0
    assert all(t.created_at is None for t in store.query())
    assert store.settings()["dark_mode"] is True
    assert (store.path.parent / "legacy-backup" / "todos.ini").read_text(encoding="utf-8") == original
    assert (legacy / "todos.ini").read_text(encoding="utf-8") == original
    report = store.weekly_report(datetime.now().date())
    assert not report["created"]
    store.close()

def test_corrupt_and_future_database_not_overwritten(tmp_path):
    path = tmp_path / "bad.sqlite3"
    path.write_bytes(b"this is not a database")
    with pytest.raises(sqlite3.DatabaseError): TaskStore(path)
    assert path.read_bytes() == b"this is not a database"
    future = tmp_path / "future.sqlite3"
    with sqlite3.connect(future) as db: db.execute("PRAGMA user_version=99")
    with pytest.raises(RuntimeError): TaskStore(future)

def test_weekly_boundary_reopen_dedup_and_immutable_history(tmp_path):
    now = [datetime(2026, 12, 28, 0, 0, tzinfo=ZONE)]
    store = TaskStore(tmp_path / "week.sqlite3", clock=lambda: now[0])
    task = store.add("年末工作")
    store.complete(task.id)
    report = store.weekly_report(date(2026, 12, 28), zone=ZONE)
    assert len(report["created"]) == len(report["completed"]) == 1
    store.reopen(task.id)
    assert not store.weekly_report(date(2026, 12, 28), zone=ZONE)["completed"]
    now[0] += timedelta(days=1)
    store.complete(task.id)
    store.complete(task.id)
    now[0] = datetime(2027, 1, 4, 0, 0, tzinfo=ZONE)
    next_week = store.add("下周事项")
    store.update(task.id, text="新的一周修改")
    store.reopen(task.id)
    old = store.weekly_report(date(2027, 1, 3), zone=ZONE)
    assert old["monday"] == date(2026, 12, 28)
    assert len(old["created"]) == len(old["completed"]) == 1
    assert old["completed"][0]["text"] == "年末工作"
    assert next_week.id not in {t["id"] for t in old["created"]}
    assert "每周总结" in store.report_markdown(old)
    store.close()

def test_reminder_cancel_edit_restart_and_resume(tmp_path):
    now = datetime(2026, 10, 8, 12, tzinfo=ZONE)
    store = TaskStore(tmp_path / "reminders.sqlite3", clock=lambda: now)
    task = store.add("到时提醒", remind_at=now-timedelta(minutes=1))
    completed = store.add("完成后不提醒", remind_at=now-timedelta(minutes=1))
    deleted = store.add("删除后不提醒", remind_at=now-timedelta(minutes=1))
    store.complete(completed.id)
    store.trash(deleted.id)
    assert [t.id for t in store.pending_reminders()] == [task.id]
    store.mark_reminders_sent([task.id])
    store.update(task.id, text="只改内容")
    assert not store.pending_reminders()
    store.close()
    store = TaskStore(tmp_path / "reminders.sqlite3", clock=lambda: now)
    assert not store.pending_reminders()
    store.update(task.id, remind_at=now+timedelta(minutes=1))
    assert not store.pending_reminders()
    assert [t.id for t in store.pending_reminders(now+timedelta(hours=1))] == [task.id]
    store.close()
