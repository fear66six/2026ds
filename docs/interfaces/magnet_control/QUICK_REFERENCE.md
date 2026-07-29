# 电磁铁控制现场速查

## 链路

```text
Jetson → ATK-MO340P → STM32F103C8T6 → PB12 → MOSFET → 电磁铁
```

- 串口：115200、8N1、无流控、ASCII、LF 结尾
- PA9=USART1_TX；PA10=USART1_RX；PB12=高开/低关
- 本次用户提供的 Jetson 路径：
  `/dev/serial/by-id/usb-1a86_USB_Single_Serial_5B7A030191-if00`
  （部署时复核；不要永久硬编码 `/dev/ttyACM0`）

## 命令

```text
PING                         -> PONG
GET_STATUS                   -> STATUS MAGNET=0|1 FAULT=0|1
MAGNET_ON <50..500>          -> OK ON TIMEOUT_MS=<ms>
MAGNET_OFF                   -> OK OFF
EMERGENCY_OFF                -> OK OFF
```

## 安全启动

1. 确认机械臂停止、负载接线和供电已核验。
2. 打开串口（驱动自动发送 `MAGNET_OFF`）。
3. `ping()` 必须成功。
4. `get_status()` 必须为 `magnet=False, fault=False`。
5. 只有状态机明确授权才可 `magnet_on(ms)`。

## 释放

1. `magnet_off()`。
2. `get_status()` 确认 `magnet=False`。
3. 等待约 200 ms（待实机标定）。
4. 水平侧移约 3 mm（待机械标定）。
5. 小幅抬升。
6. **视觉确认**工件已释放。

`MAGNET=0` 不等于工件已脱落。

## 紧急处理

1. 停止机械臂。
2. 尽力 `emergency_off()`。
3. 切断电磁铁负载电源。
4. 关闭串口。
5. 检查 MOSFET、降压、共地、端子和线圈；异常发热/异味时不得恢复。

## 禁止

- 无持续时间开启、超过 500 ms 单次开启或启动时自动开启
- 多进程/多线程无锁共享串口
- 用 ATK 或 STM32 GPIO 给电磁铁供电
- 把 Mock、`OK ON` 或 `MAGNET=0` 当作物理结果
- 释放失败后无限侧移、甩动或重新长时间通电
