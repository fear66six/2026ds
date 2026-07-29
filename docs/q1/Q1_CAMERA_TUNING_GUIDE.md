# Q1 摄像头调优指南

## 当前默认与实时命令

Windows 默认请求 640×480、30 FPS、MJPG；`auto` 后端在 Windows 按 DSHOW、MSMF、CAP_ANY 顺序尝试。启动时会打印后端、实际宽高、`CAP_PROP_FPS`、FOURCC 和不生效的设置，画面中还会持续显示实际读取的 Capture FPS。

```powershell
cd 2026E
python -m q1.main --camera --camera-index 1 `
  --camera-backend dshow --camera-width 640 --camera-height 480 `
  --camera-fps 30 --camera-fourcc MJPG
```

若 DSHOW 无法打开或真实读取帧率低，再用完全相同参数比较 `--camera-backend msmf`。不要回到 848×480 作为默认模式，除非基准确认它是该摄像头的原生高帧率模式。

## 先跑三组基准

在项目根目录运行，每组至少 300 帧：

```powershell
python tools/q1_camera_benchmark.py capture_only --camera-index 0 --frames 300
python tools/q1_camera_benchmark.py capture_display --camera-index 0 --frames 300
python tools/q1_camera_benchmark.py capture_display_detect --camera-index 0 --frames 300
```

报告写入：

```text
reports/q1_camera_benchmark_windows.json
reports/q1_camera_benchmark_windows.md
reports/q1_camera_benchmark_linux.json
reports/q1_camera_benchmark_linux.md
```

工具会记录实际协商参数、真实 FPS、read/detect 分位数、latest-frame 跳帧数、CPU、内存和可读取的 Linux 温度信息。它还会实际读取并探测常见的 640×480/1280×720、30 FPS、MJPG/YUYV 组合。

## Windows

分别比较后端：

```powershell
python tools/q1_camera_benchmark.py capture_display_detect --camera-backend dshow --camera-width 640 --camera-height 480 --camera-fps 30 --camera-fourcc MJPG
python tools/q1_camera_benchmark.py capture_display_detect --camera-backend msmf --camera-width 640 --camera-height 480 --camera-fps 30 --camera-fourcc MJPG
```

选择真实 capture/display FPS 稳定且 P95 read 延迟较低的后端，不仅看 `CAP_PROP_FPS`。若 MJPG 未协商成功，比较 YUYV；USB 带宽不足时优先 640×480@30。

## Jetson/Linux

先使用：

```bash
python tools/q1_camera_benchmark.py capture_display_detect \
  --camera-backend v4l2 --camera-index 0 \
  --camera-width 640 --camera-height 480 --camera-fps 30 --camera-fourcc MJPG
```

如果系统已有 `v4l2-ctl`，可只读检查：

```bash
v4l2-ctl --device=/dev/video0 --list-formats-ext
```

只有 OpenCV 构建和系统插件已确认时才尝试：

```bash
python tools/q1_camera_benchmark.py capture_display_detect \
  --camera-backend gstreamer --camera-index 0 \
  --camera-width 640 --camera-height 480 --camera-fps 30 --camera-fourcc MJPG
```

工具不会安装 GStreamer 或插件。显式 pipeline 使用低延迟 appsink，不会在 `auto` 模式下猜测。

## OpenCV 线程

在同一摄像头、分辨率、曝光和场景下分别运行：

```bash
python tools/q1_camera_benchmark.py capture_display_detect --opencv-threads 1
python tools/q1_camera_benchmark.py capture_display_detect --opencv-threads 2
python tools/q1_camera_benchmark.py capture_display_detect --opencv-threads 4
```

比较 detect P50/P95、display FPS、CPU 和温度。不要把线程数固定为某台开发机的最优值。

## 曝光诊断

启动诊断会打印 `auto_exposure`、`exposure`、`gain` 和白平衡读值。黑背景可能使自动曝光延长帧周期：

1. 先保持 `CAMERA_AUTO_EXPOSURE/EXPOSURE/GAIN = None` 获取基线。
2. 查摄像头驱动的数值语义；不同后端的自动曝光取值并不统一。
3. 仅在设备确认支持时修改 `q1/config.py`。
4. 每次只改一个参数，重复三组基准。
5. 以真实 capture FPS 和图像可检测性共同判断，不用降低曝光换取不可用画面。

## 验收

- 电脑：capture/display ≥25 FPS，detect 3–5 FPS。
- Jetson：capture ≥25 FPS 或设备稳定上限，display ≥20 FPS。
- 检测期间当前帧持续变化，无历史队列积压。
- result age 可见，按键响应正常。
- 若硬件达不到，保存实际模式和报告，不修改结果冒充达标。
- 纸框锁定后，纸外白块和跨安全 ROI 边界的白块显示为红色拒绝候选。
- 连续三次四模板匹配稳定后才显示 READY。
