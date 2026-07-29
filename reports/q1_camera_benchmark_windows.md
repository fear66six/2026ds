# Q1 camera benchmark: windows

- mode: `capture_display_detect`
- frames: 300
- OpenCV: `4.13.0`
- backend: `DSHOW`
- requested: `848x480 @ 30.0`
- actual: `848.0x480.0 @ CAP_PROP_FPS=30.00003000003`
- FOURCC: `YUY2`
- measured capture FPS: `30.01`
- display FPS: `30.01`
- detect FPS: `3.62`
- cap.read ms avg/P50/P95/P99: `33.30` / `32.06` / `47.70` / `48.72`
- detect ms P50/P95: `2.3563499980809866` / `13.578324999798497`
- possible skipped/latest-frame drops: `0`
- failed reads: `0`
- process CPU percent (one-core scale): `22.51`
- RSS MiB: `None`

> CAP_PROP_FPS 仅为驱动报告值；验收应使用 measured capture/display FPS。
