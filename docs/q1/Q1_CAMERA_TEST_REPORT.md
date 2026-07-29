# Q1 摄像头优化测试报告

日期：2026-07-29

## 本轮边界

- 未打开任何真实摄像头
- 未打开串口
- 未接入 NexArm、STM32、MOSFET 或电磁铁
- 未执行机械动作
- 未修改 `q2`
- 未安装软件

## 静态与离线测试

执行：

```text
python -m unittest discover -s tests/q1 -v
python -m compileall -q 2026E/q1 tools/q1_camera_benchmark.py tests/q1
python -m q1.main --help
python -m q1.main --image ..\backup\2026E\test.png --no-show
```

结果：

- 11/11 自动测试通过
- Python 编译检查通过
- 新旧 CLI 兼容入口保留，并新增 camera backend/尺寸/FPS/FOURCC/benchmark/线程选项
- 离线图片仍检测 4/4、拼合通过、最大顶点误差 1.3663501716 cm

## 修改前后结果回归

同一 `backup/2026E/test.png` 分别加载修改前 `backup/2026E/q1` 和当前 `2026E/q1`：

| 字段 | 修改前 | 修改后 |
|---|---:|---:|
| `ok` | true | true |
| pieces | 4 | 4 |
| `assembly_ok` | true | true |
| 最大顶点误差 | 1.3663501715929642 | 1.3663501715929642 |
| 四块中心坐标（6位小数） | 完全一致 | 完全一致 |

这证明当前离线样本的检测、模板匹配和目标位姿逻辑未改变；不代表所有真实摄像头场景都已验证。

## 合成慢检测验证

测试摄像头每帧写入递增值，后台 detector 人为 sleep 300 ms：

- 主线程在 1 秒限制内取得 20 个严格递增 sequence
- detector submitted 大于 processed
- pending 帧会覆盖，不形成历史队列
- 显示底图仍来自当前 frame
- 检测尺寸宽高比不匹配时坐标被忽略
- 摄像头和检测线程均能有限时间退出
- 人工抛出的检测异常被记录，线程随后可继续处理

## 硬件基准

| 平台 | Capture FPS | Display FPS | Detect FPS | Detect P50/P95 | 状态 |
|---|---:|---:|---:|---:|---|
| Windows 内置摄像头 | 未测 | 未测 | 未测 | 未测 | 等待用户运行基准工具 |
| Jetson 外接摄像头 | 未测 | 未测 | 未测 | 未测 | 等待目标机运行基准工具 |

没有用合成测试或 `CAP_PROP_FPS` 伪装真实硬件性能。
