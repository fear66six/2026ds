# K230 TTL 正式相机链路（唯一生产方案）

详细文档见：[`docs/interfaces/k230_ttl_camera/`](../../../docs/interfaces/k230_ttl_camera/)。

- **Jetson 调用接口**：[JETSON_PYTHON_API.md](../../../docs/interfaces/k230_ttl_camera/JETSON_PYTHON_API.md)
- **协议 V2**：[PROTOCOL_V2.md](../../../docs/interfaces/k230_ttl_camera/PROTOCOL_V2.md)
- **接线**：[HARDWARE_CONNECTION.md](../../../docs/interfaces/k230_ttl_camera/HARDWARE_CONNECTION.md)
- **速查**：[QUICK_REFERENCE.md](../../../docs/interfaces/k230_ttl_camera/QUICK_REFERENCE.md)

## 固定参数

UART3 TX50/RX51，460800 8N1，GC2093 **1280×720**，JPEG **q=65**，discard=2，chunk=4096。

TTL：`/dev/serial/by-id/usb-1a86_USB_Single_Serial_5B7A028646-if00`

## 目录

| 路径 | 作用 |
|---|---|
| `protocol.py` | 协议 V2 常量（根/k230/jetson 三份保持一致） |
| `k230/k230_camera_server.py` | K230 统一服务 → 拷到 `/sdcard/experiments/k230_ttl_jpeg/` |
| `k230/main_launcher.py` | 启动器 → 拷到 `/sdcard/main.py`（人工） |
| `jetson/k230_camera.py` | Jetson 正式客户端 `K230TtlSnapshotCamera` |
| `jetson/camera_smoke_test.py` | 烟雾测试 |
| `tests/test_protocol_v2.py` | 协议单元测试 |

K230 侧文件请人工放置；本仓库脚本不负责向 SD 写文件。

## Jetson 最短调用

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / "k230_ttl_camera"))
from k230_camera import K230TtlSnapshotCamera

with K230TtlSnapshotCamera() as cam:
    frame = cam.capture_snapshot()  # (720,1280,3) BGR
    print(cam.last_meta)
```

```bash
cd ~/k230_ttl_camera && python3 camera_smoke_test.py --count 5
```

## 接线

TTL TX→K230 RX51，TTL RX←K230 TX50，GND 共地，**不接 VCC**。
