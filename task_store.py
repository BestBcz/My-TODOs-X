"""Transactional local storage. UI state never serves as the source of truth."""
from __future__ import annotations

import json
import shutil
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Callable

UTC = timezone.utc
UNCATEGORIZED = "uncategorized"


def utc_now() -> datetime:
    return datetime.now(UTC)


def stamp(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        value = value.astimezone()
    return value.astimezone(UTC).isoformat(timespec="microseconds")


@dataclass(frozen=True)
class Task:
    id: str
    text: str
    category_id: str = UNCATEGORIZED
    priority: int = 1
    pinned: bool = False
    position: int = 0
    status: str = "active"
    trashed: bool = False
    due_at: str | None = None
    remind_at: str | None = None
    reminder_sent_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    completed_at: str | None = None
    trashed_at: str | None = None


class TaskStore:
    def __init__(self, path: Path | str, clock: Callable[[], datetime] = utc_now):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        self.db = sqlite3.connect(str(self.path), timeout=5)
        self.db.row_factory = sqlite3.Row
        try:
            self.db.execute("PRAGMA foreign_keys=ON")
            version = self.db.execute("PRAGMA user_version").fetchone()[0]
            if version > 1:
                raise RuntimeError("数据来自更新版本，请使用更新版本的软件打开。")
            if self.db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise RuntimeError("数据库校验失败，请保留数据文件并从备份恢复。")
            self.db.executescript("""
                CREATE TABLE IF NOT EXISTS categories(id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE);
                CREATE TABLE IF NOT EXISTS tasks(
                    id TEXT PRIMARY KEY, text TEXT NOT NULL,
                    category_id TEXT NOT NULL REFERENCES categories(id),
                    priority INTEGER NOT NULL, pinned INTEGER NOT NULL, position INTEGER NOT NULL,
                    status TEXT NOT NULL, trashed INTEGER NOT NULL,
                    due_at TEXT, remind_at TEXT, reminder_sent_at TEXT,
                    created_at TEXT, updated_at TEXT, completed_at TEXT, trashed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS events(
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
                    kind TEXT NOT NULL, at TEXT NOT NULL, snapshot TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS events_at ON events(at, seq);
                CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT OR IGNORE INTO categories VALUES('uncategorized', '未分类');
                PRAGMA user_version=1;
            """)
        except Exception:
            self.db.close()
            raise

    def close(self):
        self.db.close()

    def categories(self) -> list[tuple[str, str]]:
        return [(r["id"], r["name"]) for r in self.db.execute(
            "SELECT * FROM categories ORDER BY (id != 'uncategorized'), name COLLATE NOCASE")]

    def category_name(self, category_id: str) -> str:
        row = self.db.execute("SELECT name FROM categories WHERE id=?", (category_id,)).fetchone()
        if row is None:
            raise ValueError("分类不存在")
        return row[0]

    def add_category(self, name: str) -> str:
        name = name.strip()
        if not name:
            raise ValueError("分类名称不能为空")
        category_id = uuid.uuid4().hex
        with self.db:
            self.db.execute("INSERT INTO categories VALUES(?,?)", (category_id, name))
        return category_id

    def rename_category(self, category_id: str, name: str):
        name = name.strip()
        if category_id == UNCATEGORIZED or not name:
            raise ValueError("默认分类不能修改，分类名称不能为空")
        self.category_name(category_id)
        with self.db:
            self.db.execute("UPDATE categories SET name=? WHERE id=?", (name, category_id))
            for row in self.db.execute("SELECT * FROM tasks WHERE category_id=?", (category_id,)).fetchall():
                self._event(self._task(row), "update")

    def delete_category(self, category_id: str):
        if category_id == UNCATEGORIZED:
            raise ValueError("默认分类不能删除")
        self.category_name(category_id)
        with self.db:
            for row in self.db.execute("SELECT * FROM tasks WHERE category_id=?", (category_id,)).fetchall():
                self._update(self._task(row).id, category_id=UNCATEGORIZED)
            self.db.execute("DELETE FROM categories WHERE id=?", (category_id,))

    @staticmethod
    def _task(row) -> Task:
        values = dict(row)
        values["pinned"] = bool(values["pinned"])
        values["trashed"] = bool(values["trashed"])
        return Task(**values)

    def get(self, task_id: str) -> Task:
        row = self.db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            raise ValueError("事项不存在，可能已被删除")
        return self._task(row)

    def _event(self, task: Task, kind: str):
        snapshot = asdict(task)
        snapshot["category_name"] = self.category_name(task.category_id)
        if kind == "delete":
            snapshot["deleted"] = True
        self.db.execute("INSERT INTO events(task_id,kind,at,snapshot) VALUES(?,?,?,?)",
                        (task.id, kind, stamp(self.clock()), json.dumps(snapshot, ensure_ascii=False)))

    def _add(self, text: str, category_id=UNCATEGORIZED, priority=1, pinned=False,
             due_at=None, remind_at=None, imported=False) -> Task:
        if not text.strip():
            raise ValueError("请输入待办内容")
        if priority not in (0, 1, 2):
            raise ValueError("优先级无效")
        self.category_name(category_id)
        now = stamp(self.clock())
        position = self.db.execute("SELECT COALESCE(MAX(position),-1)+1 FROM tasks").fetchone()[0]
        task = Task(uuid.uuid4().hex, text, category_id, priority, bool(pinned), position,
                    due_at=stamp(due_at), remind_at=stamp(remind_at),
                    created_at=None if imported else now, updated_at=now)
        values = asdict(task)
        self.db.execute(f"INSERT INTO tasks({','.join(values)}) VALUES({','.join('?' for _ in values)})",
                        tuple(values.values()))
        self._event(task, "import" if imported else "create")
        return task

    def add(self, text: str, **fields) -> Task:
        with self.db:
            return self._add(text, **fields)

    def _update(self, task_id: str, kind="update", **fields) -> Task:
        self.get(task_id)
        allowed = set(Task.__dataclass_fields__) - {"id", "created_at", "updated_at", "position"}
        if set(fields) - allowed:
            raise ValueError("包含不可修改的字段")
        if "text" in fields and not fields["text"].strip():
            raise ValueError("请输入待办内容")
        if "category_id" in fields:
            self.category_name(fields["category_id"])
        if "priority" in fields and fields["priority"] not in (0, 1, 2):
            raise ValueError("优先级无效")
        for key in ("due_at", "remind_at", "completed_at", "trashed_at", "reminder_sent_at"):
            if key in fields:
                fields[key] = stamp(fields[key])
        if "remind_at" in fields and fields["remind_at"] != self.get(task_id).remind_at:
            fields["reminder_sent_at"] = None
        fields["updated_at"] = stamp(self.clock())
        self.db.execute(f"UPDATE tasks SET {','.join(k+'=?' for k in fields)} WHERE id=?",
                        (*fields.values(), task_id))
        task = self.get(task_id)
        self._event(task, kind)
        return task

    def update(self, task_id: str, **fields) -> Task:
        if set(fields) - {"text", "category_id", "priority", "pinned", "due_at", "remind_at"}:
            raise ValueError("事项状态请通过完成、恢复和回收站接口修改")
        with self.db:
            return self._update(task_id, **fields)

    def complete(self, task_id: str) -> Task:
        task = self.get(task_id)
        if task.trashed:
            raise ValueError("请先从回收站恢复事项")
        if task.status == "completed":
            return task
        with self.db:
            return self._update(task_id, "complete", status="completed", completed_at=self.clock())

    def reopen(self, task_id: str) -> Task:
        task = self.get(task_id)
        if task.trashed:
            raise ValueError("请先从回收站恢复事项")
        if task.status == "active":
            return task
        with self.db:
            return self._update(task_id, "reopen", status="active", completed_at=None)

    def complete_many(self, task_ids: list[str]):
        with self.db:
            for task_id in task_ids:
                task = self.get(task_id)
                if task.trashed:
                    raise ValueError("请先从回收站恢复事项")
                if task.status != "completed":
                    self._update(task_id, "complete", status="completed", completed_at=self.clock())

    def trash(self, task_id: str) -> Task:
        if self.get(task_id).trashed:
            return self.get(task_id)
        with self.db:
            return self._update(task_id, "trash", trashed=True, trashed_at=self.clock())

    def restore(self, task_id: str) -> Task:
        if not self.get(task_id).trashed:
            return self.get(task_id)
        with self.db:
            return self._update(task_id, "restore", trashed=False, trashed_at=None)

    def delete(self, task_id: str):
        task = self.get(task_id)
        if not task.trashed:
            raise ValueError("只有回收站中的事项可永久删除")
        with self.db:
            self._event(task, "delete")
            self.db.execute("DELETE FROM tasks WHERE id=?", (task_id,))

    def query(self, status="active", search="", category_id=None, sort="manual") -> list[Task]:
        tasks = [self._task(r) for r in self.db.execute("SELECT * FROM tasks")]
        tasks = [t for t in tasks if (t.trashed if status == "trash" else not t.trashed and t.status == status)]
        if category_id:
            tasks = [t for t in tasks if t.category_id == category_id]
        if search:
            tasks = [t for t in tasks if search.casefold() in t.text.casefold()]
        keys = {
            "manual": lambda t: (t.position, t.id),
            "due": lambda t: (t.due_at is None, t.due_at or "", t.position),
            "priority": lambda t: (-t.priority, t.position),
            "created": lambda t: (t.created_at is None, t.created_at or "", t.position),
        }
        if sort not in keys:
            raise ValueError("排序方式无效")
        return sorted(tasks, key=lambda t: (not t.pinned, keys[sort](t)))

    def delete_many(self, task_ids: list[str]):
        with self.db:
            for task_id in task_ids:
                task = self.get(task_id)
                if not task.trashed:
                    raise ValueError("只有回收站中的事项可永久删除")
                self._event(task, "delete")
                self.db.execute("DELETE FROM tasks WHERE id=?", (task_id,))

    def reorder(self, ordered_ids: list[str]):
        if len(set(ordered_ids)) != len(ordered_ids):
            raise ValueError("排序包含重复事项")
        expected = self.query()
        if set(ordered_ids) != {t.id for t in expected}:
            raise ValueError("只能对完整的未完成清单排序")
        pinned = {t.id for t in expected if t.pinned}
        if ordered_ids[:len(pinned)] and set(ordered_ids[:len(pinned)]) != pinned:
            raise ValueError("置顶事项必须排在前面")
        with self.db:
            for position, task_id in enumerate(ordered_ids):
                self.db.execute("UPDATE tasks SET position=? WHERE id=?", (position, task_id))

    def pending_reminders(self, now: datetime | None = None) -> list[Task]:
        return [self._task(r) for r in self.db.execute(
            "SELECT * FROM tasks WHERE status='active' AND trashed=0 AND remind_at<=? "
            "AND reminder_sent_at IS NULL ORDER BY remind_at", (stamp(now or self.clock()),))]

    def mark_reminders_sent(self, task_ids: list[str]):
        with self.db:
            for task_id in task_ids:
                self.db.execute("UPDATE tasks SET reminder_sent_at=? WHERE id=? AND status='active' AND trashed=0",
                                (stamp(self.clock()), task_id))

    def settings(self) -> dict:
        return {r[0]: json.loads(r[1]) for r in self.db.execute("SELECT key,value FROM settings")}

    def save_settings(self, values: dict):
        with self.db:
            self.db.executemany("INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                                [(k, json.dumps(v, ensure_ascii=False)) for k, v in values.items()])

    @staticmethod
    def legacy_texts(path: Path) -> list[str]:
        return [text for text in path.read_text(encoding="utf-8-sig").split("<TODO-START-MARK>")[1:]
                if text.strip()]

    def import_legacy(self, path: Path | str) -> int:
        texts = self.legacy_texts(Path(path))
        with self.db:
            for text in texts:
                self._add(text, imported=True)
        return len(texts)

    def migrate_legacy(self, directory: Path | str) -> int:
        if self.db.execute("SELECT 1 FROM metadata WHERE key='legacy_migrated'").fetchone():
            return 0
        directory = Path(directory)
        files = [directory / name for name in ("todos.ini", "options.ini") if (directory / name).is_file()]
        if not files:
            return 0
        backup = self.path.parent / "legacy-backup"
        backup.mkdir(exist_ok=True)
        for source in files:
            target = backup / source.name
            if not target.exists():
                shutil.copy2(source, target)
        texts = self.legacy_texts(directory / "todos.ini") if (directory / "todos.ini").exists() else []
        mapping = {"USE_DARK_MODE": "dark_mode", "FIXED_POSITION": "position_locked",
                   "FIXED_POSITION_X": "window_x", "FIXED_POSITION_Y": "window_y"}
        values = {}
        if (directory / "options.ini").exists():
            for line in (directory / "options.ini").read_text(encoding="utf-8-sig").splitlines():
                key, sep, value = line.partition("=")
                key, value = key.strip(), value.strip()
                if sep and key in mapping:
                    if key in ("USE_DARK_MODE", "FIXED_POSITION"):
                        if value in ("True", "False"):
                            values[mapping[key]] = value == "True"
                    else:
                        try:
                            values[mapping[key]] = int(value)
                        except ValueError:
                            pass
        with self.db:
            for text in texts:
                self._add(text, imported=True)
            # Keep migration, settings and import events within one transaction.
            for key, value in values.items():
                self.db.execute("INSERT OR IGNORE INTO settings VALUES(?,?)", (key, json.dumps(value)))
            self.db.execute("INSERT INTO metadata VALUES('legacy_migrated',?)", (str(directory.resolve()),))
        return len(texts)

    def weekly_report(self, selected: date, now: datetime | None = None, zone: tzinfo | None = None) -> dict:
        now = now or self.clock()
        local_now = now.astimezone(zone)
        monday = selected - timedelta(days=selected.weekday())
        if monday > local_now.date():
            raise ValueError("不能生成未来周的总结")
        start_local = datetime.combine(monday, time.min)
        end_local = start_local + timedelta(days=7)
        start = stamp(start_local.replace(tzinfo=zone) if zone else start_local.astimezone())
        end = stamp(end_local.replace(tzinfo=zone) if zone else end_local.astimezone())
        cutoff = min(end, stamp(now))
        states, created, completions = {}, {}, {}
        for row in self.db.execute("SELECT * FROM events WHERE at<? AND at<=? ORDER BY at,seq", (end, stamp(now))):
            snapshot = json.loads(row["snapshot"])
            states[row["task_id"]] = snapshot
            if start <= row["at"] < end and row["kind"] == "create":
                created[row["task_id"]] = snapshot
            if row["kind"] == "complete":
                completions[row["task_id"]] = snapshot
        completed = [completions[k] for k, value in states.items()
                     if value["status"] == "completed" and k in completions
                     and start <= (value["completed_at"] or "") < end
                     and (value["completed_at"] or "") <= cutoff]
        pending = [v for v in states.values() if v["status"] == "active"
                   and not v["trashed"] and not v.get("deleted")]
        overdue = [v for v in pending if v["due_at"] and v["due_at"] < cutoff]
        groups = {}
        for task in completed:
            name = task["category_name"]
            groups[name] = groups.get(name, 0) + 1
        return {"monday": monday, "sunday": monday + timedelta(days=6), "created": list(created.values()),
                "completed": completed, "pending": pending, "overdue": overdue, "groups": groups}

    @staticmethod
    def report_markdown(report: dict) -> str:
        lines = [f"# 每周总结 · {report['monday']} 至 {report['sunday']}", "",
                 f"新增 {len(report['created'])} 项 · 完成 {len(report['completed'])} 项 · "
                 f"待办 {len(report['pending'])} 项 · 逾期 {len(report['overdue'])} 项", ""]
        for key, title in (("created", "本周新增"), ("completed", "本周完成"),
                           ("pending", "待办事项"), ("overdue", "逾期事项")):
            lines.extend([f"## {title}", ""])
            if not report[key]:
                lines.append("暂无事项。")
            for task in report[key]:
                text = task["text"].replace("\n", "\n  ")
                lines.append(f"- {text}（{task['category_name']}）")
            lines.append("")
        lines.extend(["## 完成事项分类汇总", ""])
        lines.extend(f"- {name}：{count} 项" for name, count in sorted(report["groups"].items()))
        return "\n".join(lines) + "\n"
