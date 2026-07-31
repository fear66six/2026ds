# Q3 Playing-Card Puzzle

Q3 reuses the completed Q1 K230 capture, A4 detection, paper-to-arm calibration,
NexArm transfer sequence and STM32 magnet session. Only card-fragment detection,
pattern matching and assembly solving differ.

The card solver was integrated from `2026E-7.31/q3/card_solver`. Production Q3
first uses Q1 paper detection and rectifies the board to portrait A4 coordinates,
then solves the white playing-card fragments and centres the assembled card in
the lower half.

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
transfer timing, serial endpoints and magnet lease as Q1.
