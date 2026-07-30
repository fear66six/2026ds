# Q1 参考坐标系

实机调试时，所有纸面位置、目标矩形、机械臂指令都按本文解释。  
坐标不一致时，先查本节，再改标定文件，不要先改碎片模板。

## 1. 坐标系总览

```text
相机像素 (px)
    │ vision.detect_paper 检测 A4 四角
    ▼
A4 纸面坐标 (mm 或 cm，左上原点，x 右，y 下)
    │ ArmCoordinateMapper.paper_to_robot
    ▼
NexArm 笛卡尔坐标 (x,y,z) + pitch/roll/claw
```

| 名称 | 原点 | 轴向 | 单位 | 代码位置 |
|---|---|---|---|---|
| 相机像素 | 图像左上 | x 右，y 下 | px | `vision` / OpenCV |
| A4 纸面 | A4 左上角 | x 右，y 下 | cm 或 mm | `config.py` / `analyzer` |
| 图 2 局部 | 目标矩形左上角 | x 右，y 下 | cm | `pieces.py` |
| NexArm | 机械臂基座坐标系 | 厂商 SDK 定义 | SDK 单位（通常 mm） | `nexarm_sdk.set_pose` |

**源码确认**：纸面与图 2 局部均采用“左上原点、y 向下”，与图像坐标同向。  
**待实机验证**：NexArm 基座轴向、零位、正方向（见 `docs/TODO_VERIFY.md` V-007）。

## 2. A4 纸面坐标

### 2.1 尺寸（源码确认）

| 量 | 值 | 来源 |
|---|---|---|
| 宽 | 21.0 cm | `config.A4_WIDTH_CM` |
| 高 | 29.7 cm | `config.A4_HEIGHT_CM` |
| 上下分界线 y | 14.85 cm | `DIVIDER_Y_CM = A4_HEIGHT_CM / 2` |

- **上半区**：`y < divider` → 源碎片区（`UPPER_SOURCE`）
- **下半区**：`y ≥ divider` → 目标拼接区（`LOWER_TARGET`）

### 2.2 单位换算（源码确认）

| 换算 | 关系 |
|---|---|
| cm → mm | ×10 |
| mm → cm | ÷10 |
| 规划/判定内部 | 多用 **mm**（`vertices_mm`、`target_origin_mm`） |
| 模板定义 | 多用 **cm**（`pieces.PIECE_TEMPLATES`） |

## 3. 图 2 目标矩形（局部坐标）

### 3.1 外框（赛题 + 源码）

- 总尺寸：**10 cm × 6 cm**
- 局部原点：目标矩形左上角 `(0, 0)`
- 换算：赛题图若以左下为原点、y 向上，则 `y_code = 6 - y_figure`

```text
(0,0) ----2cm---- (2,0) -------------- (10,0)
  |                 \                    |
 2cm                 \ 对角线             |
  |                   \                  |
(0,2) ----→ A(3.6,1.2)                   |
  |1cm                \                  |
(0,3) --------→ B(7.6,4.2)               |
  |3cm                      \            |
(0,6) ------------------------ (10,6)
```

命名点（`pieces.py`）：

| 符号 | 局部坐标 (cm) | 含义 |
|---|---|---|
| `DIAG_TOP` | (2.0, 0.0) | 主对角线起点（顶边距左 2 cm） |
| `DIAG_POINT_A` | (3.6, 1.2) | 距 `DIAG_TOP` 约 2 cm |
| `DIAG_POINT_B` | (7.6, 4.2) | 距右下角 (10,6) 约 3 cm |
| `RECT_BOTTOM_RIGHT` | (10.0, 6.0) | 矩形右下角 |

四片：`P1` 左上四边形、`P2` 左中、`P3` 左下、`P4` 右侧大三角。  
面积和不变量用 `pieces.verify_geometry_invariants()` 校验（期望总面积 60 cm²）。

### 3.2 目标矩形在 A4 上的放置（工程决策）

代码默认把图 2 放在下半区：

| 量 | 值 | 计算 |
|---|---|---|
| 左上角 x | 5.5 cm = **55.0 mm** | `(21 - 10) / 2` |
| 左上角 y | 16.85 cm = **168.5 mm** | `14.85 + 2.0` |
| 配置字段 | `target_origin_mm = (55.0, 168.5)` | `runtime_config.py` |

含义：水平居中，上边缘距分界线 **2 cm**。

**工程决策**：赛题未规定目标矩形在下半区的绝对位置；当前采用上述默认。若实机要改位置，改 `Q1RuntimeConfig.target_origin_mm`（或后续做成标定字段），并同步更新本文。

世界坐标（纸面 mm）：

```text
world_mm = template_local_cm * 10 + target_origin_mm
```

## 4. 纸面检测（像素 → A4）

正式路径不再使用静态 `--paper-calibration` JSON。每帧通过
`vision.detect_paper(frame)` 从实图检测 A4 四角，再映射到纸面坐标。

| 量 | 含义 | 来源 |
|---|---|---|
| `corners_px` | A4 四角像素，顺序 TL, TR, BR, BL | `detect_paper` |
| `px_per_cm` | 像素到厘米尺度 | `detect_paper` |
| `divider_y_cm` | 上下分界线 | `detect_divider_line` 或默认半高 |

检测失败时本轮场景无效，不进入抓放。

**待实机验证**：当前安装姿态下 `detect_paper` 对横放 A4 的稳定性和角点抖动（V-008）。

## 5. 机械臂标定（纸面 mm → NexArm）

文件：`--robot-config q1/config/robot_config.json`。机械臂矩阵、腕部、HOME、
高度、运动参数、到位判定、工作区和稳定设备端口集中在该文件中。

### 5.1 位置矩阵

| 字段 | 形状 | 行为 |
|---|---|---|
| `paper_to_robot_matrix` | 3×3 或 4×4 | `ArmCoordinateMapper.paper_to_robot` |

- **3×3**：`[rx, ry, w]^T = H · [x_mm, y_mm, 1]^T`，再齐次归一；`z` 直接用配置高度
- **4×4**：`[rx, ry, rz, w]^T = H · [x_mm, y_mm, z_mm, 1]^T`

无矩阵或文件不存在 → 禁止 RealRun。

### 5.2 纸面内旋转 → 腕部 roll（工程决策 D-006）

规划得到 `rotation_delta_deg`（源轮廓刚性对齐到目标模板的旋转角），再映射：

```text
roll = wrist_roll_zero_deg + wrist_roll_sign * rotation_delta_deg
roll = clamp(roll, wrist_roll_min_deg, wrist_roll_max_deg)
```

| 字段 | 含义 |
|---|---|
| `wrist_roll_zero_deg` | 碎片目标姿态为 0° 时的腕部 roll |
| `wrist_roll_sign` | `+1` 或 `-1`，对齐纸面正转到 roll 正转 |
| `wrist_roll_min_deg` / `max` | 安全限幅 |
| `default_pitch_deg` | 默认俯仰（示例 -90） |
| `default_claw` | 夹爪字段（电磁铁方案下通常 0） |

**工程决策**：用户确认纸面内旋转走 NexArm `roll`。  
**待实机验证**：零位与符号（`docs/TODO_VERIFY.md` V-009）。小角度（±15°）验证后再写进 JSON。

### 5.3 高度与安全（来自 robot_config.json）

`--robot-config` 必填，否则禁止启动：

| 字段 | 用途 |
|---|---|
| `motion_mode` | 正式执行模式；当前必须为 `direct_pose` |
| `pick_height` | 吸取高度 z |
| `release_height` | 释放高度 z |
| `move_duration_ms` | 单步 `set_pose` 时长 |
| `magnet_settle_ms` | 吸合后等待 |
| `workspace_limits` | `x/y/z` 允许区间 |
| `home_pose` | **唯一**观察/拍照位，与复位 HOME 统一：`[x,y,z,pitch,roll,claw]` 或再加 `duration_ms` |
| `position_tolerance_mm` | 三维合成到位容差，当前用户批准为 10 mm |
| `orientation_tolerance_deg` | pitch/roll/claw 到位容差 |
| `nexarm_port` | 固定 NexArm by-id 设备路径 |

当前 HOME/观察位为 `(173,4,226,-84.4,0,0)`，时长 6000 ms，到位位置容差
10 mm。Z241 候选实测停在 Z219，已回退；工作区和历史依据见
`robot_config.json`，低高度路径仍为 UNVERIFIED。

## 6. 单步规划用的参考点

`plan_single_move`（`motion.py`）不使用 `minAreaRect` 中心/角度，而使用：

```text
rigid_placement_transform(当前顶点_mm, 目标模板顶点_mm)
→ 源质心 start_c、目标质心 end_c、旋转角 rotation_delta_deg
```

| 量 | 含义 |
|---|---|
| `pick_point_paper` | 纸面抓取参考点 = `start_c`（mm） |
| `target_pose_paper` | 纸面释放参考点 = `end_c`（mm） |
| `rotation_delta_deg` | 纸面内需转过的角 |
| `approach/transfer/rotate` | `direct_pose` 下不生成，保持 `None` 仅用于旧产物兼容 |
| `source/release` | 完整六维目标；z = pick/release 高度，`roll` = 映射后的腕部角 |

正式执行依次调用一次完整 `set_pose(source)` 和一次完整 `set_pose(release)`。
XYZ/Pitch/Roll/Claw 由同一条厂商坐标命令发送，不构造固定 XY 的竖直升降或
固定 Z 的横向转运航点。SDK 命令形式不等于物理路径已经验证：两个 Z25 目标及
源到目标的低位扫掠仍为 `UNVERIFIED`。

## 7. 运行产物里怎么核对坐标

每次闭环写入 `runs/q1/<run_id>/cycle_XX/`：

| 文件 | 看什么 |
|---|---|
| `raw.png` / `rectified.png` | 原图与纸面矫正图 |
| `overlay.png` | 检测轮廓 + **10×6 目标外框** + 四片目标边界 |
| `scene.json` | 各片 `center_mm`、`vertices_mm`、误差 |
| `single_move_plan.json` | 本轮源/目标纸面与机器人位姿 |
| `audit.json` | 是否完成、偏位、释放失败 |

调坐标时优先对比：`overlay` 上橙色目标框是否压在你期望的下半区位置。

## 8. 调坐标时的检查顺序

1. 纸面四角标定：矫正后 A4 边框是否贴齐  
2. 分界线：中线是否落在物理白线附近  
3. 目标原点：`overlay` 中 10×6 框位置  
4. 手测 1～2 个纸面点 → 机械臂点，拟合/校验 `paper_to_robot_matrix`  
5. 小角度 roll：确认 `wrist_roll_sign`  
6. 再开闭环搬一块，查 `single_move_plan.json` 与下一轮 `audit.json`

任何一步未通过，不要继续提高运动速度或通电时间。
