# Q1 实时误检静态审计

日期：2026-07-29

## 审计范围

- 当前实现：`2026E/q1/`
- 修改前基线：Git 提交 `8d6c29a`
- 原始归档核对：`backup/2026E/q1.zip`
- 本轮未修改 `q2`，未访问摄像头、串口或机械硬件

## 已确认的结构性根因

| 根因 | 修改前证据 | 影响 | 当前处理 |
|---|---|---|---|
| 纸框最终使用水平 `boundingRect` | `vision.py::_detect_outer_mat_frame` | 旋转/透视时 ROI 包含纸外区域 | 最终输出改为 `approxPolyDP` 四边形，有限兜底为 `minAreaRect` |
| 上下黑区合并后仍返回水平框 | `vision.py::_merge_stacked_paper_frame` | 合并框纳入纸外背景 | 合并轮廓点后拟合真实四边形 |
| ROI 只做中心收缩 | `vision.py::_inner_roi_mask` | 不是 A4 坐标下的严格上半区 | 新增厘米坐标透视映射的上半区安全 ROI |
| 候选仅按中心判断 | `vision.py::_contour_to_piece` | 纸外物体只要中心落入即可通过 | 计算完整候选的安全区覆盖率并检测边界接触 |
| 超大轮廓会被拆分 | `vision.py::detect_pieces` | 反光区域可变成多个假碎片 | 实时路径超过 30 cm² 直接拒绝，不做拆分 |
| 纸框周期替换 | 原 `LiveDetector` 缓存策略 | 一次错误可能持续约 6.7 秒 | 固定相机改为 15 帧稳定自动锁定，或手工标定 |
| 历史 overlay 替换当前 frame | 原 `camera_run.py` | 检测慢时画面冻结 | 当前 frame 始终作为显示底图 |

## 拒绝规则

实时检测先在原始白色掩膜上找完整轮廓，再与上半区安全 ROI 比较。以下任一条件都不会改变为 READY：

- `TOUCHES_ROI_BORDER`
- `SAFE_INSIDE_RATIO_LOW`（初始阈值 0.98）
- `CENTER_OUTSIDE_ROI`
- `BBOX_OUTSIDE_A4`
- `CROSSES_DIVIDER`
- `OVERSIZED_LIVE_CANDIDATE`

拒绝原因保留在实时画面和 S 键诊断 JSON 中。没有通过“取面积最大的四片”强行掩盖误检。

## 保留不变的内容

- Q1 四片模板几何与面积
- 10 cm × 6 cm 目标矩形
- 离线图片流程及仿真入口
- 离线完整 `assign_pieces` 流程
- HSV、面积和反光阈值没有被反复调参来代替结构修复

## 结论边界

离线合成与历史图片回归已通过；真实相机的纸张反光、镜头畸变和曝光仍需在固定机位用诊断包验证。
