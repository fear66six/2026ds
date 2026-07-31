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

- **3×3**：`[rx, ry, w]^T = H · [x_mm, y_mm, 1]^T`，再齐次归一；`z` 默认用配置高度
- **4×4**：`[rx, ry, rz, w]^T = H · [x_mm, y_mm, z_mm, 1]^T`
- **`surface_z_plane_mm=[a,b,c]`**（可选）：接触面 `z_contact = a·x_mm + b·y_mm + c`。存在时，
  `pick_height` / `release_height` 表示 `surface_z_ref_paper_mm`（默认纸面中心 `[105,148.5]`）处的
  **绝对**机器人 Z；其它点使用  
  `z = height + (plane(x,y) - plane(ref))`，以跟随桌面/坐标系倾斜。

无矩阵或文件不存在 → 禁止 RealRun。

### 5.2 纸面内旋转 → 腕部 roll（工程决策 D-006）

规划得到 `rotation_delta_deg`（源轮廓刚性对齐到目标模板的旋转角），再映射：

```text
pick_roll = wrist_roll_zero_deg
release_roll = pick_roll + wrist_roll_sign * normalize(rotation_delta_deg)
```

当前不做软件腕部角度裁剪。

| 字段 | 含义 |
|---|---|
| `wrist_roll_zero_deg` | 碎片目标姿态为 0° 时的腕部 roll |
| `wrist_roll_sign` | `+1` 或 `-1`，对齐纸面正转到 roll 正转 |
| `default_pitch_deg` | 默认俯仰（示例 -90） |
| `default_claw` | 夹爪字段（电磁铁方案下通常 0） |

**工程决策**：用户确认纸面内旋转走 NexArm `roll`。  
**待实机验证**：零位与符号（`docs/TODO_VERIFY.md` V-009）。小角度（±15°）验证后再写进 JSON。

### 5.3 高度与运动（来自 robot_config.json）

`--robot-config` 必填，否则禁止启动：

| 字段 | 用途 |
|---|---|
| `motion_mode` | 正式执行模式；当前必须为 `direct_pose` |
| `pick_height` | 吸取高度 z；有 `surface_z_plane_mm` 时为参考点绝对 Z |
| `release_height` | 释放高度 z；有平面时同上 |
| `surface_z_plane_mm` | 接触面平面系数 `[a,b,c]` |
| `surface_z_ref_paper_mm` | 高度参考纸面点，默认 `[105,148.5]` |
| `buffer_pose` | 固定搬运缓冲位姿 `[x,y,z,pitch,roll,claw,duration_ms]` |
| `move_duration_ms` | 单步 `set_pose` 时长 |
| `magnet_settle_ms` | 吸合后等待 |
| `home_pose` | **唯一**观察/拍照位，与复位 HOME 统一：`[x,y,z,pitch,roll,claw]` 或再加 `duration_ms` |
| `position_tolerance_mm` | 三维合成到位容差，当前用户批准为 10 mm |
| `orientation_tolerance_deg` | pitch/roll/claw 到位容差 |
| `nexarm_port` | 固定 NexArm by-id 设备路径 |

当前 HOME/观察位为 `(175,0,210,-90,0,0)`，时长 3000 ms，到位位置容差
10 mm。吸取/释放名义高度为 Z=-10 / Z=-8（纸面中心参考），并随接触面平面倾斜。

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
| `approach/transfer` | 吸取后斜向抬升点与拱顶点 |
| `rotate` | 当前保持 `None`，roll 已随搬运位置渐变 |
| `source/release` | 完整六维目标；z = pick/release 高度，`roll` = 映射后的腕部角 |

正式执行先调用 `set_pose(source)`，吸合后依次调用斜向抬升点、拱顶点和
`set_pose(release)`。每段均同时改变 XY 与 Z，不构造固定 XY 的竖直升降或
固定 Z 的横向转运航点。

## 7. 运行产物里怎么核对坐标

每次运行写入 `output/runs/q1/<run_id>/`：

| 文件 | 看什么 |
|---|---|
| `capture.png` | 本次唯一生产输入图像 |
| `scene.json` | 各片 `center_mm`、`vertices_mm`、误差 |
| `piece_moves.json` | P4→P3→P2→P1 大到小队列、源/目标纸面与机器人位姿 |
| `moves/*.json` | 每片命令与执行结果 |
| `final.json` / `failure.json` | 汇总或停止原因 |

生产流程不再生成矫正图和叠加图。需要可视核对时，用 `capture.png` 运行独立离线
视觉诊断，不把调试图片生成接回生产循环。

## 8. 调坐标时的检查顺序

1. 离线检查 `capture.png` 的 A4 四角检测
2. 核对 `scene.json` 的分界线与上下区域
3. 核对 `piece_moves.json` 中 10×6 目标顶点
4. 手测 1～2 个纸面点 → 机械臂点，拟合/校验 `paper_to_robot_matrix`
5. 小角度 roll：确认 `wrist_roll_sign`
6. V-013 通过后，再按批准流程做受控单目标验证

任何一步未通过，不要继续提高运动速度或通电时间。
