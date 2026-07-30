# Q1 修正与判定标准

本文定义：什么叫“放对了”、什么叫“要修正”、以及实机该先调哪几个阈值。  
与 [COORDINATE_FRAMES.md](COORDINATE_FRAMES.md) 配套使用。

## 1. 两套标准不要混用

| 标准 | 来源 | 用途 |
|---|---|---|
| **赛题评分** | `docs/E题_拼图装置.pdf` 第 2 页 | 相邻碎片对应顶点距离 ≤ **2 cm**；无重叠；位置正确 |
| **代码闭环判定** | `SceneAnalyzer` + `Q1RuntimeConfig` | 决定本轮是否 `PLACED_OK`、是否再搬一次 |

闭环容差默认 **严于** 赛题 2 cm，用于提前纠偏。实机若过度重试，可略放宽代码容差，但不要宽过赛题评分。

## 2. 单片状态机（源码确认）

每片模板 `P1`–`P4` 的状态：

| 状态 | 含义 | 后续动作 |
|---|---|---|
| `UNPLACED` | 仍在上半区或未到目标 | 可作为搬运候选 |
| `PLACED_OK` | 下半区且三项误差都合格 | 本片不再搬 |
| `PLACED_OFFSET` | 已在下半区但不合格 | **优先修正这片** |
| `MISSING` | 本轮未识别到 | 触发重拍/分析失败路径 |
| `RELEASE_UNCONFIRMED` | （审计侧）上一动作目标片又回到未放置 | **最高优先重做释放失败片** |

区域划分：碎片中心 `y` 相对分界线 → `UPPER_SOURCE` / `LOWER_TARGET`。

## 3. PLACED_OK 三项误差（源码确认）

对下半区碎片，同时满足才算放好：

| 误差 | 定义 | 默认阈值 | 配置字段 |
|---|---|---|---|
| 中心误差 | `‖检测中心 − 目标顶点均值中心‖` | ≤ **5.0 mm** | `place_center_tolerance_mm` |
| 角度误差 | 轮廓刚性对齐到目标模板的旋转角绝对值 | ≤ **5.0°** | `place_angle_tolerance_deg` |
| 顶点误差 | 循环/镜像对齐后的最大顶点距离 | ≤ **8.0 mm** | `vertex_max_error_mm` |

角度**不用** `cv2.minAreaRect` 的 `angle`（对不规则片不稳定），而用：

```text
compute_rigid_align_error(当前顶点_mm, 目标模板顶点_mm) → rot_deg
angle_error = |normalize(rot_deg)|
```

顶点误差允许起点错位与轮廓方向翻转（`_cyclic_vertex_error`）。

任一超限 → `PLACED_OFFSET`，下一轮会优先修正。

## 4. 整景审计与选片优先级（源码确认）

`audit_scene` 后，`select_next_piece` 优先级：

1. **释放失败**（上一动作目标片本轮仍是 `UNPLACED`/`MISSING`）→ 立刻重做该片  
2. **偏位修正**（`PLACED_OFFSET`）→ 先修正编号较小者  
3. **未放置** → 动态打分选一块（置信度、边缘、净空、移动距离等）

其它审计规则：

| 规则 | 默认 | 含义 |
|---|---|---|
| `remaining_move_tolerance_mm` | 3.0 mm | 未搬动片若中心移动超过此值，记录警告并用最新场景 |
| `all_complete` | 四片皆 `PLACED_OK` 且场景有效 | 进入 `FINAL_VERIFY` / `COMPLETED` |
| `requires_reanalysis` | `scene_valid == false` | 重拍，受 `max_visual_retries`（默认 2）限制 |

## 5. 单步修正怎么算（规划标准）

修正不是“随便往目标中心挪一点”，而是：

```text
rigid_placement_transform(当前轮廓, 图2目标顶点)
→ 新的抓取点、释放点、纸面旋转角
→ 映射到 NexArm XY + roll + 高度序列
```

执行相位（真机）：接近吸取 → 吸合等待 → 抬升 → 转移 → 释放高度 → 松磁 → 可选侧移 peel → 回观察。

释放后 `release_confirmed` 先为假，**以下一轮视觉审计为准**。

## 6. 与赛题 2 cm 的关系（工程决策）

| 层级 | 建议用法 |
|---|---|
| 闭环 `vertex_max_error_mm=8` | 约 0.8 cm，用于过程纠偏 |
| 赛题 ≤ 2 cm | 最终人工/裁判验收底线 |
| `config.VERTEX_MATCH_TOLERANCE_CM=2.0` | 历史评分向评价接口用；主闭环以 `runtime_config` 三项为准 |

实机若视觉噪声大、反复 `PLACED_OFFSET`：可先把顶点容差调到 **10～15 mm**，仍远小于 20 mm 赛题线；同时优先改善标定与光照，而不是一味放宽容差。

## 7. 实机调参顺序（推荐）

按顺序做，不要跳步：

1. **只开相机 + 纸面标定**  
   看 `rectified.png` / `overlay.png`：外框、分界线、四片轮廓  
2. **确认目标框**  
   overlay 上 10×6 与四片目标边是否落在你要的下半区位置  
3. **手测纸面→臂坐标**  
   写 `paper_to_robot_matrix`，先不准旋转  
4. **标定腕部 roll**  
   小角度验证 `wrist_roll_sign` / zero（V-009）  
5. **填 safety JSON**  
高度、工作区、`magnet_settle_ms`
6. **单片闭环**  
   只允许搬 1～2 片，查 `audit.json` 三项误差  
7. **再调容差**  
   仅当标定稳定后，微调 `place_*` / `vertex_max_error_mm`

## 8. 常见现象对照

| 现象 | 优先怀疑 | 处理 |
|---|---|---|
| 每轮都 `scene_valid` 失败 | 光照/阈值/纸面标定 | 重拍标定，查 `warnings` |
| 总判 `PLACED_OFFSET` 但肉眼已拼好 | 目标原点偏了或角度定义 | 查 overlay 目标框；核对刚性角 |
| 搬走后审计说释放失败 | 电磁铁/高度/目标位姿 | 查 `magnet` 与完整释放位姿；勿先改模板 |
| 放偏方向固定 | `paper_to_robot_matrix` 或轴向反了 | 重标矩阵，勿改图 2 顶点凑数 |
| 旋转方向反了 | `wrist_roll_sign` | 改为 `-1` 或重测零位 |
| 超过 `max_cycles` | 容太严或识别抖动 | 查 cycle 目录误差曲线再放宽容差 |

## 9. 禁止事项

- 不要用改 `PIECE_TEMPLATES` 顶点去“凑”错误的机械臂坐标  
- 不要把示例 JSON 数值直接当真机安全高度  
- 不要在未确认工作区边界时开 `--auto-start`  
- 不要把赛题 2 cm 误当成“中心误差可以到 2 cm”——赛题说的是**相邻顶点**

## 10. 关键源码索引

| 主题 | 文件 |
|---|---|
| 默认容差 | `runtime_config.py` |
| PLACED_OK 判定 | `analyzer.py::_classify_templates` |
| 审计/完成 | `auditor.py` |
| 选片与修正优先 | `selector.py` |
| 刚性规划 | `motion.py` / `geometry.py` |
| 图 2 几何 | `pieces.py` |
| 启动门禁 | `runtime_config.real_run_blockers` / `main.py` |
