# 电磁铁控制接口

本目录是视觉程序、NexArm 状态机与主控制程序调用电磁铁的统一入口。它描述当前代码真实提供的接口，并把源码事实、真实日志、报告和本次实机观察分开标注；详细证据见 [SOURCE_TRACEABILITY.md](SOURCE_TRACEABILITY.md)。

## 系统边界

```text
Jetson ─USB─> ATK-MO340P ─USART1/115200 8N1─> STM32F103C8T6
                                                     │
                                                    PB12
                                                     │
                                                   MOSFET ─> 电磁铁
```

- Jetson 不直接控制 MOSFET，只向 STM32 发送串口命令。
- STM32 负责 PB12 输出、持续时间限制和超时自动关闭。
- 当前固件不实现 USB CDC；STM32 Micro-USB 不能作为该固件的通信接口。
- `STATUS MAGNET=0` 仅表示 STM32 的软件状态与 PB12 输出锁存状态为关，不证明线圈无电流，也不证明工件已经物理脱落。
- 物理释放必须由视觉、位置变化或受限的机械剥离动作确认。

## 当前验证状态

| 项目 | 状态 | 证据 |
|---|---|---|
| 固件烧录、CubeProgrammer Verify、独立回读 | 已记录成功 | C：烧录报告 |
| `MAGNET_OFF`、`PING` 10/10、`GET_STATUS` | 有真实串口日志 | B |
| `MAGNET_ON 50/100/500`、MOSFET 指示灯、实物吸合/释放 | 本次用户报告成功，但项目中未找到对应日志 | D |
| Jetson 固定 `by-id` 路径及最终供电接线 | 本次用户提供，尚无项目日志/厂商资料交叉确认 | D/U |

## 推荐 Python 入口

当前公开入口是：

- `SerialTransport(port, baudrate=115200, timeout=1.0)`
- `STM32MagnetUART(transport)`
- `preferred_linux_port()`
- `MockTransport`

详见 [JETSON_PYTHON_API.md](JETSON_PYTHON_API.md)。`preferred_linux_port()` 只在 `by-id` 目录恰好有一个条目时返回它，并不会识别特定 ATK 设备；生产程序应由配置提供已核验的 `by-id` 路径。

## 最小安全示例

```python
from drivers.stm32_magnet_uart import SerialTransport, STM32MagnetUART

port = "/dev/serial/by-id/usb-1a86_USB_Single_Serial_5B7A030191-if00"
transport = SerialTransport(port=port)

with STM32MagnetUART(transport) as magnet:
    if not magnet.ping():
        raise RuntimeError("STM32 PING failed")
    status = magnet.get_status()
    if status.magnet or status.fault:
        raise RuntimeError(f"unsafe initial status: {status}")
```

`open()` 会先发送 `MAGNET_OFF`，上下文退出时也会关闭输出。启用必须在上层状态机明确授权后显式调用 `magnet.magnet_on(timeout_ms)`，取值仅允许 50–500 ms；不得在启动、循环空闲或导入阶段自动启用。

## 文档导航

- [HARDWARE_CONNECTION.md](HARDWARE_CONNECTION.md)：接线、供电边界与未确认项
- [STM32_UART_PROTOCOL.md](STM32_UART_PROTOCOL.md)：线级协议和错误行为
- [JETSON_PYTHON_API.md](JETSON_PYTHON_API.md)：真实 Python API、异常和示例
- [PICK_RELEASE_WORKFLOW.md](PICK_RELEASE_WORKFLOW.md)：吸取、释放、视觉确认和剩磁恢复
- [MAGNET_SAFETY.md](MAGNET_SAFETY.md)：STM32、Jetson、机械臂及硬件分层安全
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md)：现场故障排查
- [QUICK_REFERENCE.md](QUICK_REFERENCE.md)：比赛现场速查
- [SOURCE_TRACEABILITY.md](SOURCE_TRACEABILITY.md)：结论与证据定位
- [DRIVER_AUDIT.md](DRIVER_AUDIT.md)：当前驱动静态审计
- [DRIVER_IMPROVEMENT_PROPOSAL.md](DRIVER_IMPROVEMENT_PROPOSAL.md)：不改现有驱动的改进方案
- [CHANGELOG.md](CHANGELOG.md)：文档变更

## 当前接口限制

单次开启最长 500 ms；没有 `HOLD`、通信看门狗、电流传感器、吸取传感器或反向消磁。重复发送 `MAGNET_ON` 会重置截止时间，但当前驱动没有受控续租接口，不能据此假定可安全完成长时间搬运。完整限制见 [PICK_RELEASE_WORKFLOW.md](PICK_RELEASE_WORKFLOW.md#当前接口限制)。
