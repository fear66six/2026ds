import json
from pathlib import Path

from q1.main import build_controller, parse_args
from q1.runtime_config import Q1RuntimeConfig


def test_cli_exposes_only_real_run_options():
    parser = parse_args([])
    assert not hasattr(parser, "mode")
    assert not hasattr(parser, "image")


def test_real_run_requires_wrist_roll_mapping(tmp_path: Path):
    robot_path = tmp_path / "robot.json"
    robot_path.write_text(
        json.dumps({"paper_to_robot_matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]}),
        encoding="utf-8",
    )
    blockers = Q1RuntimeConfig(
        mode="run",
        robot_config=robot_path,
        nexarm_port="COM3",
        magnet_port="COM4",
        pick_height=40.0,
        release_height=38.0,
        move_duration_ms=1500,
        magnet_settle_ms=200,
    ).real_run_blockers()
    assert any("腕部 roll" in item for item in blockers)


def test_build_controller_blocks_without_calibration(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    args = parse_args(["--confirm", "RUN_Q1"])
    try:
        build_controller(args)
    except RuntimeError as exc:
        assert "REAL_RUN_BLOCKED" in str(exc)
    else:
        raise AssertionError("expected RealRun blockers")
