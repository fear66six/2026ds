# Q1 标定 JSON 模板

复制后改名去掉 `.example`，填入**实机测量值**。字段含义与调参顺序见：

- [../COORDINATE_FRAMES.md](../COORDINATE_FRAMES.md)
- [../CORRECTION_STANDARDS.md](../CORRECTION_STANDARDS.md)

| 文件 | 对应参数 |
|---|---|
| `paper_calibration.example.json` | `--paper-calibration` |
| `arm_calibration.example.json` | `--arm-calibration`（含腕部 roll） |
| `safety_config.example.json` | `--safety-config` |

示例内数值仅表示字段形状，禁止直接用于真机运动。
