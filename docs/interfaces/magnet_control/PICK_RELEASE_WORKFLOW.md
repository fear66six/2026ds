# 吸取与释放工作流

本文给上层视觉、NexArm 和主状态机定义控制边界。机械臂函数均为**伪代码**，不是已确认的 NexArm API。电磁铁调用使用当前真实 Python API。

## 吸取流程

```text
到达吸取预备位
  → 下移至已标定吸附高度
  → 确认机械臂静止/动作阶段确定
  → magnet.magnet_on(validated_duration_ms)
  → 检查串口无异常
  → 执行已标定抬升
  → 视觉/位置变化确认工件被带起
  → 成功，或进入安全恢复
```

伪代码：

```python
# move_*、vision.* 是状态机伪接口，不代表 NexArm SDK 已实现这些名称。
move_to_pick_ready_pose()
move_to_pick_height()
wait_until_arm_settled()

magnet.magnet_on(validated_duration_ms)  # 真实 API；只能是 50..500
move_to_safe_lift_pose()

if not vision.confirm_piece_picked():
    magnet.magnet_off()
    stop_arm_safely()
    enter_pick_recovery()
```

`OK ON` 只证明固件接受命令并设置 PB12；不证明 MOSFET、线圈或工件状态。吸取成功必须由视觉或经实机验证的动作/位置条件确认。

## 搬运持续时间

当前单次 `MAGNET_ON` 最长 500 ms。项目没有证据证明一次 500 ms 足以覆盖任一完整搬运轨迹。重复 `MAGNET_ON` 会在源码层重置 deadline，但当前没有 `HOLD`、续租序号、通信看门狗或线程安全的续控器；不应通过临时循环盲目续发来绕过限制。

在投入完整搬运前只能二选一：

1. 将实测且留有裕量的“吸取到释放”轨迹压缩在 500 ms 内，并记录标定条件；或
2. 设计、评审并测试新的有限租约/HOLD 机制与通信看门狗。

二者均尚未由当前项目证据确认。

## 释放流程

本次用户报告：断电后可能因剩磁和大面积贴合而不立即脱落；薄非磁性胶带/垫片、短暂等待和小幅侧移剥离可帮助释放。项目中没有对应传感器日志或视频，以下标记为 D，位移/等待量必须重新标定。

```text
到达安全放置点
  → magnet.magnet_off()
  → get_status() 确认 MAGNET=0
  → 等待约 200 ms（标定值）
  → 水平侧移约 3 mm（标定值）
  → 向上抬升
  → 视觉确认工件留在放置区
```

伪代码：

```python
move_to_place_pose()
wait_until_arm_settled()

magnet.magnet_off()                         # 真实 API
status = magnet.get_status()                # 真实 API
if status.magnet:
    raise RuntimeError("STM32 still reports magnet on")

time.sleep(calibrated_release_wait_s)       # 初始候选约 0.2 s
move_relative_xy(calibrated_peel_mm, 0)     # 初始候选约 3 mm；伪接口
move_relative_z(safe_lift_mm)               # 伪接口

if not vision.confirm_piece_released():     # 伪接口
    run_release_recovery()
```

胶带/垫片会增加气隙并可能降低最大吸力。其材料、厚度、耐磨性、位置以及吸取裕量都必须在目标工件上标定。

## 释放失败恢复

```text
首次释放
  → 视觉检查
  → 若仍粘连：
       保持 MAGNET_OFF
       再等待约 100 ms（候选）
       反方向小幅侧移
       受限的轻微升/降形成剥离
       再次视觉检查
  → 仍失败：
       停止自动流程
       保持关闭并停止机械臂
       请求人工处理
```

恢复动作必须有次数、位移、速度、加速度和工作区边界上限。禁止无限循环侧移、释放失败后重新长时间通电、未经环境检测的大幅甩动，或把 `MAGNET=0` 直接当作完成。

## 状态机建议

```text
SAFE_OFF
  └─安全检查通过─> PICK_READY
       └─限时开启─> PICK_VERIFY
            ├─失败─> RECOVERY_OFF
            └─成功且时限策略已证明─> TRANSPORT
                    └─到位─> RELEASE_OFF
                         └─侧移/抬升─> RELEASE_VERIFY
                              ├─失败且未超限─> RELEASE_RECOVERY
                              ├─失败且超限─> MANUAL_STOP
                              └─成功─> SAFE_OFF
```

任何串口异常、视觉不确定、动作超时、碰撞风险或状态机越界都进入 `RECOVERY_OFF`：停止机械臂、尽力 `EMERGENCY_OFF`、关闭通信，并由现场安全机制切断负载电源。

## 当前接口限制

- 单次开启 50–500 ms，可能短于完整搬运时间。
- `MAGNET` 只读软件变量和 PB12 ODR，不测真实电流。
- 无电流传感器、吸取检测器、物理释放检测器。
- 当前单向 MOSFET 不能反转线圈极性；没有已实现的 H 桥反向消磁。
- 侧移剥离依赖机械臂坐标、工件间距和场地标定。
- 胶带/垫片可能降低吸力并随磨损改变效果。
- 放置区必须预留侧移空间，避免扰动相邻拼图块。

未来可评估：有限租约式 `HOLD`、通信看门狗、电流检测、机械顶料/刮料结构、吸取传感器、H 桥反向消磁、视觉释放确认。以上均未实现。
