# Q1 摄像头性能审计

## 范围与证据

本次仅处理 `2026E/q1/`、Q1 专用测试、基准工具和本目录报告。正式路径在任务开始时不存在，因此从未追踪的 `backup/2026E/q1/` 原样恢复了基线；`backup/2026E/q2/` 未复制、未修改。

事实来源：

- `2026E/q1/config.py`：实时检测间隔和摄像头默认参数
- 修改前快照 `backup/2026E/q1/camera_run.py`：预览选择 `last_overlay`
- 修改前快照 `backup/2026E/q1/device_run.py`：运行预览选择 `last_overlay`
- `2026E/q1/live_detect.py`、`camera_run.py`、`device_run.py`：当前实现
- `tests/q1/`：合成帧、慢检测、关闭和回归测试

没有打开真实摄像头，因此本文不包含硬件 FPS。

## 根因确认

1. `LIVE_DETECT_MIN_INTERVAL_S = 0.28`，后台检测理论上最多约 3.57 次/秒；检测本身超过 280 ms 时会更低。
2. 修改前 `camera_run.py` 的 `_to_display()` 在检测成功后把 `last_overlay` 作为整张显示源。摄像头即使持续采集，检测结果未更新期间窗口像素保持不变，主观帧率被锁在检测频率附近。
3. 修改前 `device_run.py` 同样用 `last_overlay` 生成实时 preview，存在相同冻结。
4. 修改前 `configure_camera()` 只请求 width、height 和 buffersize，没有请求/核验 FPS、FOURCC、后端、曝光或实际协商值。
5. 修改前 `main.py` 无条件优先 `CAP_DSHOW`；该后端仅适用于 Windows。
6. 修改前 `_cm_to_px()`、`_px_to_cm()` 每点重复计算透视矩阵，纸张 ROI 和形态学 kernel 也重复创建。

## 已实施的小范围优化

- 显示底图始终是当前摄像头 frame；最近检测结果只提供纸框、碎片和状态坐标。
- 检测分辨率和显示分辨率等宽高比时缩放纸框；比例不一致时忽略坐标，不混合旧整图。
- `LiveDetector` 改为单槽 latest-frame，替换未处理帧并记录 dropped；异常记录到结果和日志，线程继续运行。
- 新增 `LatestFrameCamera` 独立采集线程，单槽保存最新帧；保留 `use_threaded_capture=False` 同步 fallback。
- Windows `auto` 依次尝试 DSHOW、MSMF、默认后端；Linux `auto` 尝试 V4L2、默认后端；GStreamer 仅显式选择且先检查 OpenCV 构建信息。
- GStreamer appsink 使用 `drop=true max-buffers=1 sync=false`。
- 配置和启动诊断覆盖 width、height、FPS、FOURCC、buffersize、自动曝光、曝光、增益和白平衡读取。
- `PaperFrame` 缓存双向透视矩阵和 ROI；目标点批量变换；形态学 kernel 模块级复用。
- 实时 pipeline 仍保留反光、面积和安全过滤，但不执行 `assign_pieces`、完整规划或动画；只有空格触发完整 pipeline。
- 纸框按首次、画面变化、最长缓存时间或 `force_refresh()` 刷新，不再只依赖固定次数。

## 显示指标

实时窗口分别显示：

- `CAP FPS`
- `DISPLAY FPS`
- `DETECT FPS`
- `DETECT MS`
- `RESULT AGE MS`
- `PIECES n/4`

这些指标不能相互替代。检测保持 3–5 Hz 并不妨碍显示达到摄像头实际可提供的帧率。

## 尚未验证

- Windows 内置摄像头在 DSHOW/MSMF 下的稳定模式和真实帧率
- Jetson 外接摄像头的 `/dev/video*`、MJPG/YUYV 能力和 V4L2/GStreamer表现
- 黑背景下自动曝光是否拉长帧周期
- 目标平台 1/2/4 OpenCV 线程的 CPU、温度和检测延迟
- 真实预览端到端延迟是否 ≤150 ms

使用 [Q1_CAMERA_TUNING_GUIDE.md](Q1_CAMERA_TUNING_GUIDE.md) 的三组基准命令获取这些结论。
