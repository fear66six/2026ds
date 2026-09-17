# STM32 第三方构建依赖

公开仓库不再追踪纯第三方 ARM/ST 支持源码。两个固件工程仍引用这些文件，因此从全新克隆构建前，需要从与工程目标及版本匹配的官方软件包恢复对应目录。

## 本地排除目录

```text
firmware/stm32f103_uart_magnet/cmsis/
firmware/stm32f103_uart_magnet/startup/
firmware/stm32f103ve_uart_magnet/cmsis/
firmware/stm32f103ve_uart_magnet/startup/
```

当前本地副本的文件头显示：

- `core_cm3.c/.h`：ARM CMSIS Cortex-M3，版本 V1.30，2009；
- `stm32f10x.h`、`system_stm32f10x.h`：STMicroelectronics STM32F10x CMSIS 设备文件，版本 V3.4.0，2010；
- `startup_stm32f10x_md.s` / `startup_stm32f10x_hd.s`：STMicroelectronics 启动文件。

不要用“较新版本”直接覆盖后编译；先确认目标 MCU、启动文件密度、头文件兼容性、链接脚本和许可证。第三方文件恢复后仍应保持未追踪状态。

## 继续追踪的混合来源文件

`src/system_stm32f10x.c` 源自 ST 文件，但当前工程包含本项目的上电安全修改，因此没有作为纯第三方副本移除。其原始 ST 版权和免责声明必须保留。

## 来源与可信度

| 结论 | 来源 | 类型 | 可信等级 | 是否需验证 |
|---|---|---|---|---|
| 纯第三方目录及版本 | 各文件头的版权、版本和日期 | 第三方源码原文 | A | 重新取得文件时需核对哈希/版本 |
| `system_stm32f10x.c` 含项目安全修改 | 当前源码 `SystemInit` 附近及 `docs/interfaces/magnet_control/` 的追溯记录 | 当前源码与项目文档 | A | 构建后仍需硬件验证 |
