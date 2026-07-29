import json
from pathlib import Path

from q1.main import build_controller, parse_args
from q1.runtime_config import Q1RuntimeConfig


def test_cli_exposes_only_real_run_options():
    parser = parse_args([])
    assert not hasattr(parser, "mode")
    assert not hasattr(parser, "image")


def test_real_run_requires_wrist_roll_mapping(tmp_path: Path):
    arm_path = tmp_path / "arm.json"
    arm_path.write_text(
        json.dumps({"paper_to_robot_matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]}),
        encoding="utf-8",
    )
    blockers = Q1RuntimeConfig(
        mode="run",
        arm_calibration=arm_path,
        paper_calibration=tmp_path / "paper.json",
        nexarm_port="COM3",
        magnet_port="COM4",
        safe_height=120.0,
        pick_height=40.0,
        release_height=38.0,
        move_duration_ms=1500,
        magnet_settle_ms=200,
        release_peel_delta=(0.0, 5.0, 10.0),
        workspace_limits={"x": (0.0, 300.0), "y": (-200.0, 200.0), "z": (0.0, 250.0)},
    ).real_run_blockers()
    assert any("腕部 roll" in item for item in blockers)


def test_build_controller_blocks_without_calibration(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    args = parse_args(["--nexarm-port", "COM3", "--magnet-port", "COM4"])
    try:
        build_controller(args)
    except RuntimeError as exc:
        assert "RealRun禁止启动" in str(exc)
    else:
        raise AssertionError("expected RealRun blockers")
