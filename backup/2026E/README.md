# E题 拼图装置

第一问与第二问**完全独立**，互不 import、互不影响。

## 目录结构

```
2026E/
├── main.py              # 统一入口（无 --q2 → 第一问，有 --q2 → 第二问）
├── q1/                  # 第一问（图2 固定四片 10×6）
│   ├── main.py          # 独立入口: python -m q1.main ...
│   ├── config.py
│   ├── pieces.py
│   ├── vision.py
│   ├── puzzle_solver.py
│   ├── geometry.py
│   ├── motion.py
│   ├── pipeline.py
│   ├── animator.py
│   ├── simulator.py
│   ├── device_run.py
│   └── executor.py
└── q2/                  # 第二问（现场 1~4 片，目标 9×5~12×9）
    ├── main.py          # 独立入口: python -m q2.main ...
    ├── config.py
    ├── vision.py        # 独立视觉（与 q1 无共享）
    ├── geometry.py
    ├── motion.py
    ├── animator.py
    ├── executor.py
    ├── assignment.py
    ├── solver.py
    ├── pipeline.py
    └── ...
```

## 第一问

```powershell
python -m q1.main --image test.png --simulate
python -m q1.main --scattered b --simulate
python -m q1.main --run --dry-run

# 或使用统一入口（等价）
python main.py --image test.png --simulate
```

## 第二问

```powershell
python -m q2.main --q2-scattered --simulate
python -m q2.main --image q2_scattered.png --simulate
python -m q2.main --image test.png --target-width 10 --target-height 6 --fig2-fallback
python -m q2.main --run --dry-run

# 或使用统一入口（等价）
python main.py --q2 --q2-scattered --simulate
```

## 安装

```powershell
pip install -r requirements.txt
```
