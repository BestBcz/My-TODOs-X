"""Run the packaged executable with isolated data and working directories."""
import json
import os
import shutil
import sqlite3
import subprocess
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def run(executable, profile, cwd):
    assert profile.resolve().is_relative_to((ROOT / "build").resolve())
    profile.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    args = [str(executable), "--data-dir", str(profile)]
    log = profile / "mytodos.log"
    previous_log_size = log.stat().st_size if log.exists() else 0
    first = subprocess.Popen(args, cwd=cwd, env=env)
    try:
        deadline = time.monotonic()+15
        while time.monotonic() < deadline:
            if first.poll() is not None: raise RuntimeError(f"程序提前退出：{first.returncode}")
            if log.exists() and b"Application ready" in log.read_bytes()[previous_log_size:]: break
            time.sleep(.1)
        else: raise RuntimeError("程序未完成启动")
        second = subprocess.run(args, cwd=cwd, env=env, timeout=10)
        if second.returncode != 0: raise RuntimeError(f"重复启动未成功唤回：exit={second.returncode}, first={first.poll()}")
        time.sleep(2)
        if first.poll() is not None: raise RuntimeError("事件循环运行时退出")
        with sqlite3.connect(profile / "mytodos.sqlite3") as db:
            assert db.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert b"Unhandled" not in log.read_bytes()[previous_log_size:]
        print(json.dumps({"executable": str(executable), "startup": "ok", "single_instance": "ok", "database": "ok"}, ensure_ascii=False))
    finally:
        first.terminate()
        first.wait(timeout=10)

def main():
    original = ROOT / "dist" / "My-TODOs-X"
    copied = ROOT / "build" / "中文 路径" / "My TODOs X"
    assert copied.resolve().is_relative_to((ROOT / "build").resolve())
    shutil.copytree(original, copied, dirs_exist_ok=True)
    cwd = ROOT / "build" / "qa" / "different-working-directory"
    cwd.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex[:8]
    run(original / "My-TODOs-X.exe", ROOT / "build" / "qa" / f"smoke-plain-{run_id}", cwd)
    run(original / "My-TODOs-X.exe", ROOT / "build" / "qa" / f"smoke-plain-{run_id}", cwd)
    run(copied / "My-TODOs-X.exe", ROOT / "build" / "qa" / f"smoke-中文 空格-{run_id}", cwd)

if __name__ == "__main__": main()
