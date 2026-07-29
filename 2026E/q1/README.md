# Q1 实机调试文档（主参考）

本目录文档是 **Q1 实机调试的主参考**。调参、对坐标、改容差时先看这里，再回源码核对。

| 文档 | 用途 |
|---|---|
| [COORDINATE_FRAMES.md](COORDINATE_FRAMES.md) | 参考坐标系、单位换算、标定 JSON、姿态映射 |
| [CORRECTION_STANDARDS.md](CORRECTION_STANDARDS.md) | 放置/修正判定标准、闭环纠偏逻辑、调参顺序 |
| [examples/](examples/) | 标定与安全参数 JSON 模板（数值须实机替换） |

## 任务边界（赛题）

- 来源：`docs/E题_拼图装置.pdf` 第 2 页图 2（可信等级 B）
- 四片同色碎片：上半区 → 下半区，拼成 **10 cm × 6 cm** 矩形
- 评分相关：相邻碎片对应顶点距离 ≤ **2 cm**（赛题评分）；代码内部闭环容差更严，见 [CORRECTION_STANDARDS.md](CORRECTION_STANDARDS.md)

## 程序做什么

每轮：**观察位 → 抓拍 → 分析四片 → 审计 → 只选并搬 1 块 → 再观察**。

生产入口只走真实链路：

```text
SnapshotCamera → SceneAnalyzer → plan_single_move
  → NexArmRobotExecutor + STM32MagnetController
```

命令（在 `2026E/` 下）：

```powershell
python -m q1.main `
  --camera-index 1 `
  --paper-calibration path\to\paper.json `
  --arm-calibration path\to\arm.json `
  --safety-config path\to\safety.json `
  --nexarm-port COMx `
  --magnet-port COMy
```

缺标定或缺安全参数时，`real_run_blockers()` 会直接拒绝启动，不会伪造默认坐标。

## 证据类型约定

文档中统一标注：

- **源码确认**：以当前 `2026E/q1/*.py` 为准
- **赛题确认**：以 `docs/E题_拼图装置.pdf` 为准
- **工程决策**：项目主动选择，可改但要同步改代码与本文档
- **待实机验证**：当前不能当物理事实使用

## 安全

未经明确批准：不打开真实串口、不发送运动、不通电磁铁。  
示例 JSON 中的数字只是字段形状模板，**禁止原样用于真机运动**。
