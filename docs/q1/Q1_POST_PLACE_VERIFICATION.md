# Q1 单块放置后复检

复检使用单张 Snapshot 和已知模板预测位置，不改变初始模板身份。

检查四类对象：

- 当前碎片：目标ROI、中心/角度/顶点误差和图像释放确认
- 历史碎片：是否偏离已确认目标位姿
- 未搬碎片：是否仍在原源位姿附近
- 全局场景：清晰度、A4角点移动、异物、反光和重叠

主要结果：

- `PASS`：继续下一块
- `PASS_WITH_SOURCE_UPDATE`：仅更新未搬碎片源位姿并增加计划版本
- `PLACE_OFFSET_CORRECTABLE`：输出二次拾取/微调建议，当前DryRun暂停
- `RELEASE_FAILED`：目标位置未确认释放；只生成保持关闭、等待、侧移剥离和再复检建议
- `PLACED_PIECE_MOVED`、`CAMERA_MOVED`、`IMAGE_INVALID`：停止并显示原因

软件命令状态不等于物理释放；只有图像确认碎片位于目标纸面位置时，`release_confirmed`才为真。
