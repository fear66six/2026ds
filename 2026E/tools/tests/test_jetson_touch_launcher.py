from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parents[1]
LAUNCHER_PATH = TOOLS_DIR / "jetson_touch_launcher.py"


def _load_launcher():
    spec = importlib.util.spec_from_file_location(
        "jetson_touch_launcher",
        LAUNCHER_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["jetson_touch_launcher"] = module
    spec.loader.exec_module(module)
    return module


launcher = _load_launcher()
write_runtime_robot_config = launcher.write_runtime_robot_config
GAP_MAX_MM = launcher.GAP_MAX_MM
GAP_MIN_MM = launcher.GAP_MIN_MM


def test_write_runtime_robot_config_writes_gap_fields(tmp_path, monkeypatch) -> None:
    base_config = tmp_path / "robot_config.json"
    base_config.write_text(
        json.dumps({"edge_gap_enabled": True, "edge_gap_mm": 5.0}),
        encoding="utf-8",
    )
    runtime_path = tmp_path / "runtime.json"

    import jetson_touch_launcher as launcher_module

    monkeypatch.setattr(launcher_module, "BASE_ROBOT_CONFIG", base_config)
    monkeypatch.setattr(launcher_module, "RUNTIME_CONFIG_PATH", runtime_path)

    result = write_runtime_robot_config(True, 6.5)
    assert result == runtime_path
    data = json.loads(runtime_path.read_text(encoding="utf-8"))
    assert data["edge_gap_enabled"] is True
    assert data["edge_gap_mm"] == 6.5


def test_write_runtime_robot_config_clamps_on_write(tmp_path, monkeypatch) -> None:
    base_config = tmp_path / "robot_config.json"
    base_config.write_text(json.dumps({"edge_gap_mm": 5.0}), encoding="utf-8")
    runtime_path = tmp_path / "runtime.json"

    import jetson_touch_launcher as launcher_module

    monkeypatch.setattr(launcher_module, "BASE_ROBOT_CONFIG", base_config)
    monkeypatch.setattr(launcher_module, "RUNTIME_CONFIG_PATH", runtime_path)

    write_runtime_robot_config(False, 99.0)
    data = json.loads(runtime_path.read_text(encoding="utf-8"))
    assert data["edge_gap_enabled"] is False
    assert data["edge_gap_mm"] == 99.0


def test_gap_bounds_constants() -> None:
    assert GAP_MIN_MM <= 5.0 <= GAP_MAX_MM
