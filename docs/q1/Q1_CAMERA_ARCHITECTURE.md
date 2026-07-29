# Q1 摄像头架构

## 数据流

```text
VideoCapture
    │ cap.read()（独立线程）
    ▼
LatestFrameCamera：单槽 latest frame + timestamp + sequence
    ├──────────────> 主线程：当前 frame → 轻量画框 → resize → imshow
    │                                    ▲
    └─ submit latest ─> LiveDetector ────┘
                        单槽 pending
                        低频 run_pipeline(live=True)
                        只发布结构化结果与指标

空格：
当前 frame → 完整 run_pipeline → 原有匹配、规划、动画/执行入口
```

采集、显示和检测不共享历史帧队列。检测忙时，新提交帧覆盖旧 pending 帧；显示继续消费摄像头最新 sequence。

## `LatestFrameCamera`

- 独立 daemon 线程执行 `cap.read()`
- 只保留一个最新 frame
- `read_latest(last_sequence)` 返回时间戳、sequence 和 `repeated`
- 连续读取失败达到有限上限后停止
- `close()` 设置停止标志、release capture 并有限时间 join
- 指标：capture FPS、read 平均/P50/P95/P99、失败次数

同步 fallback 仍由 `run_camera_q1(..., use_threaded_capture=False)` 保留。

## `LiveDetector`

结果包含：

- `paper`
- `divider_y_cm`
- `pieces`
- `all_pieces`
- `lower_piece_count`
- `evaluation`
- `detect_timestamp`
- `detect_duration_ms`
- `detect_frame_shape`

不保存或返回整张历史 overlay。指标包含 submitted、processed、dropped、detect FPS、last/average detect ms、result age 和异常。

`snapshot()` 深复制共享结构，外部修改不会改变线程内状态。

## 当前帧绘制

`render_live_result(current_frame, result)`：

1. 复制当前 frame 作为底图。
2. 检查检测帧与当前帧宽高比。
3. 比例兼容时缩放 `PaperFrame.corners_px`，碎片 cm 坐标保持不变。
4. 在当前帧上调用 `draw_overlay_live()`。
5. 比例不兼容时返回未标注的当前帧，并显示提示。

因此旧检测只可能让框的位置较旧，不会让摄像头画面本身冻结或产生整图重影。

## 平台后端

```text
Windows auto: CAP_DSHOW → CAP_MSMF → CAP_ANY
Linux auto:   CAP_V4L2  → CAP_ANY
GStreamer:    仅显式选择；检查 OpenCV build；固定低延迟 appsink
```

设置是否生效以启动后 `CAP_PROP_*` 实际值和真实帧率为准，不以 `set()` 返回值为准。
