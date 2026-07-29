"""第二问测试用例：生成图片 + 元数据"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from .simulator import generate_q2_scattered_image


@dataclass
class Q2TestMeta:
    width_cm: float
    height_cm: float
    n_pieces: int
    seed: int


def save_q2_test_case(
    path_prefix: str | Path = "q2_scattered",
    width_cm: float = 10.0,
    height_cm: float = 6.0,
    n_pieces: int = 4,
    seed: int = 42,
) -> tuple[np.ndarray, Q2TestMeta]:
    prefix = Path(path_prefix)
    img = generate_q2_scattered_image(width_cm, height_cm, n_pieces, seed=seed)
    meta = Q2TestMeta(
        width_cm=float(width_cm),
        height_cm=float(height_cm),
        n_pieces=int(n_pieces),
        seed=int(seed),
    )
    png_path = prefix.with_suffix(".png") if prefix.suffix != ".png" else prefix
    json_path = png_path.with_suffix(".json")
    cv2.imwrite(str(png_path), img)
    json_path.write_text(json.dumps(asdict(meta), indent=2), encoding="utf-8")
    return img, meta


def load_q2_meta(image_path: str | Path) -> Optional[Q2TestMeta]:
    p = Path(image_path)
    for jp in (p.with_suffix(".json"), Path("q2_scattered.json")):
        if jp.is_file():
            data = json.loads(jp.read_text(encoding="utf-8"))
            data.pop("layout", None)
            data.pop("poker", None)
            return Q2TestMeta(**{k: data[k] for k in Q2TestMeta.__dataclass_fields__})
    return None
