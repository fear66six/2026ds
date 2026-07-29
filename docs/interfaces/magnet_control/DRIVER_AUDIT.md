# Jetson 驱动静态审计

审计对象：[`drivers/stm32_magnet_uart.py`](../../../drivers/stm32_magnet_uart.py)。本次只做 AST/静态阅读和离线检查，没有 import 硬件模块、打开串口或修改驱动。

## 结论

当前驱动具备安全的基本调用骨架：构造不连接、显式 `open()`、开机先关、严格状态解析、限时开启、退出关断、异常尽力紧急关断、上下文管理和 Mock。它可作为单进程、单线程、短事务的现有入口，但尚不适合作为多组件并发访问、长时间搬运续控或高可靠恢复层。

## 检查表

| 项目 | 结果 | 证据/说明 |
|---|---|---|
| 硬编码设备路径 | 无 | `SerialTransport` 由调用者传入 |
| `by-id` 发现 | 部分支持 | `preferred_linux_port()` 只接受目录中唯一条目，不识别 ATK |
| 构造/import 不连接 | 是 | 仅 `SerialTransport.open()` 导入并打开 pyserial |
| 打开后立即关闭输出 | 是 | `STM32MagnetUART.open()` 先发 `MAGNET_OFF` |
| `ping()` | 是 | 返回 bool；异常回复仅返回 `False` |
| `get_status()` | 是 | 严格格式和值校验 |
| 限时开启 | 是，名为 `magnet_on(timeout_ms)` | 50–500，严格回复 |
| 显式关闭 | 是，名为 `magnet_off()` | 严格要求 `OK OFF` |
| 紧急关闭 | 是，名为 `emergency_off()` | 严格要求 `OK OFF` |
| `close()` | 是 | 先 normal off，失败后 best-effort emergency |
| `try/finally` 支持 | 是 | 普通 Python 模式可用 |
| 上下文管理器 | 是 | `__enter__`/`__exit__` |
| 回复校验 | 是 | ON/OFF/status 严格；PING 为 bool |
| 超时处理 | 部分 | 不完整行抛 `TimeoutError`；无重试/重连策略 |
| 串口断开处理 | 部分 | 异常传播；部分路径尽力紧急关闭 |
| 多进程占用 | 否 | 无 lock file/flock；依赖 OS 打开失败 |
| 线程安全 | 否 | 无锁，命令和回复可能交叉 |
| `MockTransport` | 是 | 不模拟定时到期、FAULT/UART 错误 |
| 类型注解 | 是 | Transport Protocol、Status、方法参数/返回 |
| 自动化测试 | 不完整 | 有安全测试工具和 Mock，无 `tests/` 测试套件 |
| 自动恢复上次开启 | 否 | 符合安全目标 |
| 将 `MAGNET=0` 解释为物理释放 | 否 | 驱动只返回 `Status`，没有错误物理推断 |
| 操作日志 | 否 | 不记录命令、回复、延迟或状态机关联 ID |

## 真实 API 与旧示例差异

当前不存在 `MagnetController`、`turn_on()`、`timed_on()`、`turn_off()` 或 `off()`。真实名称是：

```python
SerialTransport(...)
STM32MagnetUART(transport)
client.magnet_on(timeout_ms)
client.magnet_off()
client.emergency_off()
```

文档和新代码必须使用这些名称，除非未来经过兼容迁移正式增加别名。

## 风险

1. 多线程或多组件同时调用时，写入与读取没有事务锁，可能把回复匹配给错误命令。
2. 多进程只依赖串口打开失败，无法给出明确所有权和恢复信息。
3. `preferred_linux_port()` 在多个 USB 串口时返回 `None`，在只有一个但不是 ATK 时可能误选。
4. 串口超时/断开后无显式连接状态修复或重新握手策略。
5. `ping()` 对错误回复返回 `False`，与其他方法的严格异常风格不一致。
6. Mock 的 `MAGNET_ON` 不会自动到期；非数字参数可能直接由 `int()` 抛 `ValueError`，与固件 `ERR invalid_timeout` 不同；`FAULT` 永远为 0。
7. 缺少结构化操作日志，难以把吸取/释放与视觉/机械臂状态关联。
8. 当前接口只有 500 ms 单次开启，驱动未实现受控 HOLD/租约；不能支撑未经证明的长搬运。

改进方案见 [DRIVER_IMPROVEMENT_PROPOSAL.md](DRIVER_IMPROVEMENT_PROPOSAL.md)。为保护已验证行为，本次未修改驱动。
