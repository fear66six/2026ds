# K230 TTL 相机接口

本页说明项目当前 K230 ↔ Jetson 请求式 JPEG 链路。协议事实以当前源码为准；设备节点、接线和供电仍需在目标实机复核。

## 数据流

```text
Jetson                         K230
  │                              │
  │  PING <request_id>\n         │
  │ ───────────────────────────> │
  │  PONG ...                    │
  │ <─────────────────────────── │
  │                              │
  │  CAPTURE <request_id>\n      │
  │ ───────────────────────────> │
  │  40-byte KJPG header         │
  │  JPEG payload                │
  │ <─────────────────────────── │
  │  CRC / JPEG decode / shape   │
```

K230 启动后还会发送带 session、宽高和协议版本的 `READY` 行。Jetson 客户端先完成 READY/PING 握手，再接受抓拍请求。

## 固定协议参数

| 参数 | 当前源码值 | 来源 |
|---|---:|---|
| 协议版本 | 2 | `protocol.py::PROTOCOL_VERSION` |
| 波特率 | 460800 | `protocol.py::BAUDRATE` |
| 图像尺寸 | 1280 × 720 | `protocol.py::WIDTH/HEIGHT` |
| JPEG 质量 | 65 | `protocol.py::JPEG_QUALITY` |
| 二进制头长度 | 40 bytes | `protocol.py::JPG_HEADER_SIZE` |
| 最大 JPEG | 2 MiB | `protocol.py::MAX_JPEG_BYTES` |
| K230 UART 引脚 | TX 50 / RX 51 | `protocol.py::UART_TX_PIN/UART_RX_PIN` |

40 字节小端头的布局为：

```text
MAGIC(4s) VERSION(B) STATUS(B) HEADER_LENGTH(H)
SESSION_ID(I) REQUEST_ID(I) FRAME_ID(I) CAPTURE_TIMESTAMP_MS(I)
WIDTH(H) HEIGHT(H) JPEG_LENGTH(I) CRC32(I) CAPTURE_MS(H) ENCODE_MS(H)
```

客户端校验 magic、版本、头长度、request/session、尺寸、长度、CRC32 和 JPEG 解码结果。首次失败后会重新同步并最多重试一次，具体行为以 `jetson/k230_camera.py::capture_snapshot` 为准。

## Jetson API

入口类为 `jetson/k230_camera.py::K230TtlSnapshotCamera`。构造对象不等于完成通信；上下文管理器进入时调用 `open()`，退出时关闭串口。

```python
from k230_camera import K230TtlSnapshotCamera

with K230TtlSnapshotCamera() as camera:
    frame = camera.capture_snapshot()  # NumPy BGR, shape (720, 1280, 3)
    metadata = camera.last_meta
```

默认端口只是当前样机的部署记录。迁移设备时必须使用目标机实际枚举结果，不要假定 `/dev/ttyUSB0` 或照搬仓库里的 by-id。

## 接线边界

当前项目接线记录为：

```text
USB-TTL TX  → K230 RX51
USB-TTL RX  ← K230 TX50
USB-TTL GND ↔ K230 GND
VCC         不连接
```

这是项目部署信息（D），不是对所有 K230/USB-TTL 型号通用的电气结论。接线前仍须核对双方逻辑电平、供电方式、连接器方向和共地要求。

## 文件分工

| 路径 | 作用 |
|---|---|
| `2026E/drivers/k230_ttl_camera/protocol.py` | CPython / MicroPython 共用协议常量和头编解码 |
| `.../k230/k230_camera_server.py` | K230 相机初始化、请求处理和 JPEG 发送 |
| `.../k230/main_launcher.py` | K230 端启动器 |
| `.../jetson/k230_camera.py` | Jetson 串口客户端、校验、重试和事件记录 |
| `.../tests/test_protocol_v2.py` | 无硬件协议单元测试 |

K230 侧部署必须人工确认；仓库脚本不应在未授权时写入 SD 卡或覆盖设备启动文件。

## 最小验证顺序

1. 离线运行 `python -m pytest -q 2026E/drivers/k230_ttl_camera/tests`；
2. 在 Jetson 上确认端口映射和占用情况；
3. 明确授权后运行相机 smoke test，只验证握手和取图；
4. 检查尺寸、CRC、request/session 对应关系和保存图像；
5. 最后再由 Q1/Q2/Q3 的 `plan` 模式接入，不同时启动机械臂或电磁铁。

## 证据

| 结论 | 来源与定位 | 类型 | 可信等级 | 实机验证 |
|---|---|---|---|---|
| 协议常量和 40 字节头 | `2026E/drivers/k230_ttl_camera/protocol.py` | 当前源码 | A | 不需要 |
| 客户端校验、重试和生命周期 | `jetson/k230_camera.py::K230TtlSnapshotCamera` | 当前源码 | A | 串口链路需要 |
| K230 请求处理和取图 | `k230/k230_camera_server.py::handle_capture` | 当前源码 | A | 摄像头运行需要 |
| 当前接线与 by-id | `2026E/drivers/k230_ttl_camera/README.md`、`docs/PROJECT_FACTS.md` F-013 | 项目部署记录 | D | 更换设备后需要 |
