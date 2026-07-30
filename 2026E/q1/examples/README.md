# Q1 标定 JSON 模板

复制后改名去掉 `.example`，填入**实机测量值**。字段含义与调参顺序见：

- [../COORDINATE_FRAMES.md](../COORDINATE_FRAMES.md)
- [../CORRECTION_STANDARDS.md](../CORRECTION_STANDARDS.md)

A4 四角像素不再提供静态模板，运行时由 `vision.detect_paper` 从实图检测。

机械臂正式参数不再提供分散模板，统一维护在
`../config/robot_config.json`。

示例内数值仅表示字段形状，禁止直接用于真机运动。
