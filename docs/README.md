# 项目资料导航

本页只导航真实存在的资料，不复制完整 API、协议或硬件参数。技术结论必须回到原文件核查；`.cache/docs_index/` 只用于定位。

> Git 说明：体积较大且通常不修改的厂商原件、安装包、视频、镜像、固件和资料包只保留在本地资料库，不纳入 Git。仓库只追踪本页及 `PROJECT_FACTS.md`、`DECISIONS.md`、`TODO_VERIFY.md`；克隆仓库后如需硬件开发，必须另行取得原始资料并重建索引。

## 主要资料

| 路径 | 厂商/来源 | 适用设备 | 内容简介 | 文件类型 | 推荐用途 |
|---|---|---|---|---|---|
| `docs/E题_拼图装置.pdf` | 赛题发布方 | 2026 赛区 TI 杯 E 题 | 拼图装置任务与要求原文 | 原始赛题 PDF | 核对任务边界、尺寸和评分要求 |
| `docs/板端/01 第一章 快速上手/` | 亚博智能教程资料 | Jetson Orin 系列套件 | 学习路线、快速上手、系统注意事项 | 厂商教程 PDF | 确认该套件教程中的入门流程 |
| `docs/板端/02 第二章 主板基础/` | 亚博智能教程资料，部分引用 NVIDIA | Jetson Orin 官方/SUB 套件、SUPER 相关环境 | 主板介绍、系统烧录、组件和存储 | 厂商教程 PDF | 区分载板/系统候选，核查 JetPack 环境 |
| `docs/板端/04 第四章 GPIO控制/` | 亚博智能教程资料 | Jetson Orin 系列套件 | GPIO、串口、I2C 和相关界面/引脚图 | 厂商教程 PDF | GPIO/串口任务的首要板端资料；图页须视觉检查 |
| `docs/NexArm机械臂/1.教程资料/1. 快速入门/` | 幻尔科技 Hiwonder | NexArm | 快速入门、出厂程序和附录 | 厂商教程 PDF、ZIP | 查设备使用流程和原始示例 |
| `docs/NexArm机械臂/1.教程资料/3. 运动控制/` | 幻尔科技 Hiwonder | NexArm | 运动控制教程及示例工程 | 厂商教程 PDF、ZIP | 核对该版本运动控制示例；不可直接运行 |
| `docs/NexArm机械臂/1.教程资料/4. AI视觉玩法/` | 幻尔科技 Hiwonder | NexArm 与配套视觉平台 | 视觉玩法教程及示例源码 | 厂商教程/示例 | 参考视觉流程；不得当作 Jetson API |
| `docs/NexArm机械臂/1.教程资料/6. 外部主控二次开发/` | 幻尔科技 Hiwonder | NexArm 外部 UART/Wi-Fi 控制 | 二次开发 PDF、Python SDK、示例和远程连接 | 厂商教程、SDK、ZIP | 查 NexArmClient、帧格式和通信示例 |
| `docs/NexArm机械臂/3.技术参数&图纸/1. NexArm主板原理图/` | 幻尔科技 Hiwonder | NexArm 控制器 | NexArm 控制器原理图 | 厂商原始图纸 PDF | 核查控制板架构和版本候选；须视觉检查 |
| `docs/NexArm机械臂/3.技术参数&图纸/2. 总线舵机参数和使用文档/` | 幻尔科技 Hiwonder | HX-30HM、HX-10HM、HX-65HM、HX-12H | 舵机手册、规格和通信协议 | 厂商正式 PDF | 按实际舵机型号查协议和电气参数 |
| `docs/NexArm机械臂/2.软件&工具合集/8.出厂固件及烧录工具/` | 幻尔科技 Hiwonder | NexArm/同步器 | 出厂固件与烧录工具资料 | 厂商固件/工具 | 识别固件候选；未经批准不得烧录 |
| `docs/进口芯STM32F103C8T6焊针下/STM32F103C8T6核心板文档资料/` | ST/核心板资料提供方 | STM32F103x8/B | 数据手册 | 正式数据手册 PDF | 核查 MCU 能力和复用功能 |
| `docs/进口芯STM32F103C8T6焊针下/STM32F103C8T6核心板硬件资料/` | 核心板资料提供方 | STM32F103C8T6 多种核心板变体 | MICRO、TYPE-C、最小系统板原理图及尺寸 | 原始硬件图纸 PDF | 区分实物板型并核对接头/引脚；须视觉检查 |
| `docs/进口芯STM32F103C8T6焊针下/STM32F103C8T6核心板程序资料/` | 核心板资料提供方/ST 库 | STM32F103C8T6 | 测试工程、库、构建产物 | 厂商示例源码/固件 | 静态参考初始化与构建；不代表项目电磁铁固件 |
| `docs/MOSFET驱动15A资料包/资料/` | 器件/模块销售方 | 电磁铁候选 | P20/15 与 ZHI-1727 产品手册 | 产品资料 PDF | 核对候选型号；文件名与图页冲突须保留 |
| `docs/MOSFET驱动15A资料包/接线方式/` | 模块销售方 | MOSFET 驱动与电磁铁 | 接线图片 | 原始图片 | 视觉核查端子含义；不得据此直接通电 |
| `docs/MOSFET驱动15A资料包/例程/` | 模块销售方 | Arduino、STC89、STM32F103 | 驱动示例资料包 | 厂商/销售方示例 ZIP | 仅静态参考控制逻辑 |
| `TaskSuite_E/` | 用户自建工程 | K230/WonderMK 与现有 Arduino/NexArm 代码体系 | E 题任务套件、视觉/UI、协议和机械臂控制源码 | 用户源码/说明 | 作为现有工程与历史实现参考；不能当作 Jetson API |

## 历史整理与便捷副本

| 路径 | 厂商/来源 | 适用设备 | 内容简介 | 文件类型 | 推荐用途 |
|---|---|---|---|---|---|
| `docs/_nexarm_extract/` | 用户侧解压/整理副本 | NexArm | UART/Wi-Fi Python SDK 的便捷副本 | 历史整理结果/源码副本 | 便于检索；结论回查 `docs/NexArm机械臂/1.教程资料/6. 外部主控二次开发/` 原件 |
| `docs/NexArm机械臂/1.教程资料/1. 快速入门/04 附录/05 K230视觉模块（WonderMK）使用教程和工具/` | 幻尔科技配套教程 | K230/WonderMK | K230 参考教程 | 历史/参考平台资料 | 仅供 K230 路线参考，不可迁移为 Jetson API |
| `docs/NexArm机械臂/2.软件&工具合集/6. K230视觉模块（WonderMK）使用教程和工具/` | 幻尔科技配套教程 | K230/WonderMK | 另一份 K230 工具/教程集合 | 历史/重复参考资料 | 保留用于版本比对；不是 Jetson 事实来源 |

旧资料不删除、不覆盖。发现错误时在 `PROJECT_FACTS.md` 或 `TODO_VERIFY.md` 给出当前证据，不批量改写历史文件。

## 检索

```text
python tools/update_docs_index.py
python tools/search_docs.py "NexArmClient set_pose"
python tools/search_docs.py "GPIO输出 Orin Super"
```
