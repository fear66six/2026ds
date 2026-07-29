# 变更记录

## 2026-07-29

- 初建电磁铁控制接口文档集。
- 按当前 STM32 源码确认 USART1、PB12、安全初始化、50–500 ms 定时开启、错误回复和 `FAULT` 行为。
- 按当前 Python 驱动确认 `STM32MagnetUART`、`SerialTransport`、`MockTransport` 和 `preferred_linux_port()` 的真实 API。
- 将 COM15 的 `MAGNET_OFF`、PING 10/10、`GET_STATUS` 标为真实日志证据。
- 将 `MAGNET_ON` 负载测试、MOSFET 指示灯、实际吸合、剩磁释放和 Jetson `by-id` 路径标为本次用户观察 D，未冒充项目日志。
- 加入薄非磁垫片、等待、受限侧移剥离、视觉确认及失败恢复流程。
- 记录驱动端口发现、并发、日志、Mock 一致性和长时间搬运方面的限制；仅生成改进提案，未修改代码。
- 记录全局旧决策/TODO 与当前烧录报告、本次实机观察之间的冲突。
