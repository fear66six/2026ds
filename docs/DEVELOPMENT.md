# 开发与运行指南

## 环境

建议使用 Python 3.10+。从仓库根目录创建独立环境：

```bash
python -m venv .venv
source .venv/bin/activate        # Linux / macOS
# .venv\Scripts\Activate.ps1    # Windows PowerShell
python -m pip install -r requirements-dev.txt
```

运行依赖来自 `2026E/q3/requirements.txt`，包括 NumPy、OpenCV、pyserial 和 Shapely；开发依赖额外包含 pytest。

## 离线验证

```bash
python tools/check_repo.py
python -m pytest -q
python -m compileall -q 2026E drivers tests
```

`pytest.ini` 将自动发现范围限制在项目的离线测试目录。相机压力测试、机械臂方向测试和 Windows 串口脚本不属于自动测试，必须显式运行并遵守其确认要求。

GitHub Actions 会在 Python 3.10 和 3.12 上执行同一组仓库卫生检查、语法编译和离线测试。CI 不连接任何真实硬件。

## 仅规划模式

以下命令应在 Jetson 的正式工程目录 `2026E/` 下运行。它们会访问 K230 相机，但不会打开 NexArm 或 STM32 电磁铁串口。

```bash
python3 -m q1.main plan --robot-config q1/config/robot_config.json \
  --camera-backend k230_ttl --confirm CAPTURE_AND_PLAN

python3 -m q2.main plan --robot-config q1/config/robot_config.json \
  --camera-backend k230_ttl --confirm CAPTURE_AND_PLAN

python3 -m q3.main plan --robot-config q1/config/robot_config.json \
  --camera-backend k230_ttl --confirm CAPTURE_AND_PLAN
```

默认输出位于 `2026E/output/plans/<task>/<timestamp>/`，通常包含：

- `capture.png`：输入图像；
- `plan.png`：检测与目标叠加图；
- `scene.json`：检测和求解结果；
- `piece_moves.json`：动作队列。

## 真实执行模式

真实执行会控制机械臂和电磁铁。运行前至少确认：

1. 当前设备型号、供电、接线和急停条件；
2. 三个串口持久路径分别对应 NexArm、K230 和 STM32；
3. HOME、工作区、抓放高度和全路径没有碰撞风险；
4. 当前 A4 位置对应最新标定；
5. 电磁铁限时租约和手动断电路径已验证；
6. 现场人员已明确授权本次运动。

```bash
python3 -m q1.main run --robot-config q1/config/robot_config.json \
  --camera-backend k230_ttl --magnet-backend stm32 --confirm RUN_Q1

python3 -m q2.main run --robot-config q1/config/robot_config.json \
  --camera-backend k230_ttl --magnet-backend stm32 --confirm RUN_Q2

python3 -m q3.main run --robot-config q1/config/robot_config.json \
  --camera-backend k230_ttl --magnet-backend stm32 --confirm RUN_Q3
```

这些命令只是接口说明，不构成对当前设备可安全运行的确认。

## 任务文档

- [Q1 调试与标定](../2026E/q1/README.md)
- [Q2 几何拼图](../2026E/q2/README.md)
- [Q3 扑克牌拼图](../2026E/q3/README.md)
- [K230 TTL 相机](../2026E/drivers/k230_ttl_camera/README.md)
- [电磁铁接口](interfaces/magnet_control/README.md)
- [待实机验证事项](TODO_VERIFY.md)

## 提交建议

- 不提交 `.cache/`、`output/`、`runs/`、`logs/`、`tmp/`、本地虚拟环境和固件构建目录；
- 只将少量、去敏后的代表性结果复制到 `assets/showcase/`；
- 新增硬件资料后更新文档索引，但不要提交再分发条件不明的厂商资料；
- 修改公共标定或安全逻辑时，同步更新事实、决策或待验证文档。
