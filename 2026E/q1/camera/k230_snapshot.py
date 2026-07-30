"""Thin adapter around the deployed production K230 TTL snapshot camera."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any


class K230SnapshotAdapter:
    """Load and use the existing production camera without copying its protocol."""

    def __init__(self, project_root: Path, port: str) -> None:
        self.project_root = project_root
        self.port = port
        self._module: ModuleType | None = None
        self._camera: Any = None

    def _load_module(self) -> ModuleType:
        driver_dir = self.project_root / "hardware" / "k230_ttl_camera"
        source = driver_dir / "k230_camera.py"
        if not source.is_file():
            raise RuntimeError(f"K230 camera implementation missing: {source}")
        import sys

        if str(driver_dir) not in sys.path:
            sys.path.insert(0, str(driver_dir))
        spec = importlib.util.spec_from_file_location("q1_deployed_k230_camera", source)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Cannot load K230 camera implementation: {source}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    def open_and_check(self) -> dict[str, Any]:
        self._module = self._load_module()
        self._camera = self._module.K230TtlSnapshotCamera(port=self.port)
        self._camera.initialize()
        # initialize() performs READY/STATUS and PING. Repeat public health_check
        # so the report contains a distinct current communication check.
        if not self._camera.health_check():
            raise RuntimeError("K230 health_check failed")
        return {
            "port": self.port,
            "ping": "pass",
            "status": "pass",
            "fixed_width": int(self._module.WIDTH),
            "fixed_height": int(self._module.HEIGHT),
            "fixed_baudrate": int(self._module.BAUDRATE),
        }

    def capture(self):
        if self._camera is None:
            raise RuntimeError("K230 camera is not open")
        return self._camera.capture_snapshot()

    @property
    def last_meta(self) -> dict[str, Any] | None:
        if self._camera is None or self._camera.last_meta is None:
            return None
        return dict(self._camera.last_meta.__dict__)

    def close(self) -> None:
        if self._camera is not None:
            self._camera.close()
            self._camera = None
