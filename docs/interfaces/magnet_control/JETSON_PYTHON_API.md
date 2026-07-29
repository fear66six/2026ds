# Jetson Python API

实现文件为 [`drivers/stm32_magnet_uart.py`](../../../drivers/stm32_magnet_uart.py)。导入模块、构造 `SerialTransport` 或 `STM32MagnetUART` 都不会打开硬件；必须显式调用 `open()`。

## 公开类型

### `SerialTransport`

```python
SerialTransport(port: str, baudrate: int = 115200, timeout: float = 1.0)
```

- `open() -> None`：在此时导入 `pyserial` 并以 8N1、无软/硬流控打开串口。
- `write_line(line: str) -> None`：追加 LF，ASCII 编码并 flush。
- `read_line() -> str`：等待完整 LF；不完整时抛 `TimeoutError`；非 ASCII 回复会抛解码异常。
- `close() -> None`：关闭并清空内部串口对象，可重复调用。

底层 `pyserial` 打开、写入、断开等异常原样向上传播；当前代码没有重试或自动重连。

### `Status`

```python
@dataclass(frozen=True)
class Status:
    magnet: bool
    fault: bool
```

它是 STM32 控制状态，不是线圈电流或工件释放传感器。

### `STM32MagnetUART`

```python
STM32MagnetUART(transport: Transport)
```

| 方法 | 返回 | 行为与异常 |
|---|---|---|
| `open()` | `None` | 打开 transport，立即发送 `MAGNET_OFF`；回复非 `OK OFF` 时尽力 `EMERGENCY_OFF`、关闭并抛异常 |
| `ping()` | `bool` | 仅当回复严格等于 `PONG` 时为 `True` |
| `get_status()` | `Status` | 严格解析 `STATUS MAGNET=x FAULT=y`；格式或值错误抛 `RuntimeError` |
| `magnet_on(timeout_ms: int)` | `None` | 拒绝 bool/非 int，范围 50–500；严格校验回复，异常回复时尽力紧急关闭 |
| `magnet_off()` | `None` | 严格要求 `OK OFF`；否则尽力紧急关闭并抛 `RuntimeError` |
| `emergency_off()` | `None` | 发送 `EMERGENCY_OFF`，严格要求 `OK OFF` |
| `close()` | `None` | 尝试 `magnet_off()`；失败则尽力 `EMERGENCY_OFF`；最后总会关闭 transport |

该类实现 `with` 上下文管理。异常退出时先尽力发送 `EMERGENCY_OFF`，再执行 `close()`。它没有内部锁，不应被多个线程并发调用；也没有跨进程串口锁。

### `preferred_linux_port()`

```python
preferred_linux_port() -> Optional[str]
```

它读取 `/dev/serial/by-id/`；仅当目录中恰好有一个条目时返回该路径，否则返回 `None`。它不验证 VID/PID、设备描述或预期 ATK 序列号，也不会自动传给 `SerialTransport`。

本次用户提供的曾用路径是：

```text
/dev/serial/by-id/usb-1a86_USB_Single_Serial_5B7A030191-if00
```

该路径在项目日志中没有佐证，属于 D；部署时必须在目标 Jetson 上重新确认，不能回退为永久硬编码 `/dev/ttyACM0`。

### `MockTransport`

`MockTransport` 用于离线控制流测试，不访问硬件。它并不模拟真实定时到期、UART 错误和完整 `FAULT` 语义，任何 Mock 结果都不得写成实机验证。

## 可复制示例

### 安全连接、PING 与状态

```python
from drivers.stm32_magnet_uart import SerialTransport, STM32MagnetUART

transport = SerialTransport(
    port="/dev/serial/by-id/usb-1a86_USB_Single_Serial_5B7A030191-if00",
    timeout=1.0,
)

with STM32MagnetUART(transport) as magnet:
    if not magnet.ping():
        raise RuntimeError("unexpected PING response")
    status = magnet.get_status()
    print(status)
```

### 单次限时开启与显式关闭

以下示例会真实启用负载，只能由完成接线、安全标定并获得授权的上层状态机调用：

```python
from drivers.stm32_magnet_uart import SerialTransport, STM32MagnetUART

magnet = STM32MagnetUART(SerialTransport(port=verified_by_id_path))
try:
    magnet.open()                 # 先自动 MAGNET_OFF
    if not magnet.ping():
        raise RuntimeError("STM32 unavailable")
    initial = magnet.get_status()
    if initial.magnet or initial.fault:
        raise RuntimeError(f"unsafe initial state: {initial}")

    magnet.magnet_on(200)         # 50..500 ms，必须显式授权
    # 上层立即执行已标定动作和视觉检查；不能把 OK ON 当成吸取成功。
    magnet.magnet_off()
finally:
    try:
        magnet.emergency_off()
    except Exception:
        pass
    magnet.close()
```

### Mock 离线检查

```python
from drivers.stm32_magnet_uart import MockTransport, STM32MagnetUART

with STM32MagnetUART(MockTransport()) as magnet:
    assert magnet.ping()
    assert magnet.get_status() == type(magnet.get_status())(
        magnet=False, fault=False
    )
    magnet.magnet_on(200)
    assert magnet.get_status().magnet
    magnet.magnet_off()
```

这只验证 Python 调用和回复解析；Mock 不会在 200 ms 后自动关闭。

## 集成规则

- 由配置或部署探测层提供唯一且已核验的 `by-id` 路径。
- 一个进程独占一个串口；上层用单线程/队列串行化调用。
- 启动顺序固定为 `open()`（内含 `MAGNET_OFF`）→ `ping()` → `get_status()`。
- 每次吸取/释放记录命令、单调时钟、回复、状态机阶段和视觉结果。
- 对任何通信异常：停止机械运动，尽力 `emergency_off()`，关闭串口；不能只依赖串口命令，应具备切断负载电源的现场手段。
- 驱动问题与兼容改进见 [DRIVER_AUDIT.md](DRIVER_AUDIT.md) 和 [DRIVER_IMPROVEMENT_PROPOSAL.md](DRIVER_IMPROVEMENT_PROPOSAL.md)。
