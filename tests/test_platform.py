from pathlib import Path
import sys
import pytest
from platform_services import InstanceGuard, launch_command, RUN_KEY, RUN_NAME, set_autostart

def test_source_and_frozen_command_paths(tmp_path):
    folder = tmp_path / "中文 路径"
    folder.mkdir()
    python = folder / "python.exe"
    pythonw = folder / "pythonw.exe"
    pythonw.touch()
    source = folder / "start.py"
    command = launch_command(python, False, source)
    assert str(pythonw) in command and str(source) in command
    assert command.endswith(" --autostart")
    frozen = launch_command(folder / "My-TODOs-X.exe", True)
    assert "start.py" not in frozen and '"' in frozen

@pytest.mark.skipif(sys.platform != "win32", reason="Windows registry adapter")
def test_autostart_registration_and_removal_are_scoped(monkeypatch):
    import winreg
    from unittest.mock import MagicMock
    key = object()
    context = MagicMock()
    context.__enter__.return_value = key
    create, write, delete = MagicMock(return_value=context), MagicMock(), MagicMock()
    monkeypatch.setattr(winreg, "CreateKey", create)
    monkeypatch.setattr(winreg, "SetValueEx", write)
    monkeypatch.setattr(winreg, "DeleteValue", delete)
    set_autostart(True)
    create.assert_called_with(winreg.HKEY_CURRENT_USER, RUN_KEY)
    assert write.call_args.args[1] == RUN_NAME
    assert "--autostart" in write.call_args.args[-1]
    set_autostart(False)
    delete.assert_called_with(key, RUN_NAME)

def test_single_instance_activation(qtbot, tmp_path):
    first, second = InstanceGuard(tmp_path), InstanceGuard(tmp_path)
    assert first.acquire()
    try:
        with qtbot.waitSignal(first.activated, timeout=2000):
            assert second.acquire() is False
    finally:
        first.close()
        second.close()
