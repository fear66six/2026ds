# Q3 Playing-Card Puzzle

Q3 reuses the completed Q1 K230 capture, A4 detection, paper-to-arm calibration,
NexArm transfer sequence and STM32 magnet session. Only card-fragment detection,
pattern matching and assembly solving differ.

The card solver was initially integrated from `2026E-7.31/q3/card_solver` and
updated from `D:/OIK/Downloads/q3/card_solver`. Production Q3
first uses Q1 paper detection and rectifies the board to portrait A4 coordinates,
then solves the white playing-card fragments and centres the assembled card in
the lower half.

The updated solver scores four-piece combinations when segmentation produces
extra contours, restores playing-card corner marks more robustly, and bounds
search by wall-clock time. A timeout may retain a clearly marked best-effort
assembly for diagnostics, but Q3 rejects that assembly for motion planning.

## Dependencies

Install `requirements.txt` in the same Python environment used to run Q1. Q3
adds `shapely>=2.0`; the other runtime dependencies are shared with Q1.

```bash
cd ~/2026E
python3 -m pip install -r q3/requirements.txt
```

## Plan Only

```bash
cd ~/2026E
python3 -m q3.main plan \
  --robot-config q1/config/robot_config.json \
  --camera-backend k230_ttl \
  --confirm CAPTURE_AND_PLAN
```

This writes `capture.png`, `plan.png`, `scene.json` and `piece_moves.json` under
`output/plans/q3/<timestamp>` without opening NexArm or the magnet controller.

## Complete Run

```bash
cd ~/2026E
python3 -m q3.main run \
  --robot-config q1/config/robot_config.json \
  --camera-backend k230_ttl \
  --magnet-backend stm32 \
  --confirm RUN_Q3
```

The complete run uses the same HOME, pickup/release heights, roll compensation,
transfer timing, serial endpoints and magnet lease as Q1. Q3 deliberately loads
`q1/config/robot_config.json` through `q1.calibration.ArmCoordinateMapper`, so the
Q1 calibration updates in `e7e1a290` and `2febb608` also apply to every Q3 move:

- the refitted paper-to-robot XY matrix is shared;
- pickup and release Z follow `surface_z_plane_mm` relative to
  `surface_z_ref_paper_mm`;
- the active pickup/release reference heights and pickup XY offset are loaded
  from the same file rather than duplicated in Q3.

`q3/tests/test_q1_calibration_reuse.py` guards this shared contract and checks
that Q3-generated pickup and release poses receive point-specific Z values.
