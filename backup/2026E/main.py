#!/usr/bin/env python3
"""
E题 拼图装置 — 统一入口（转发至独立模块）

第一问: python main.py --image test.png --simulate
        python -m q1.main --image test.png --simulate

第二问: python main.py --q2 --camera
        python main.py --q2 --image q2_scattered.png --simulate
"""

from __future__ import annotations

import sys


def main():
    if "--q2" in sys.argv:
        sys.argv = [a for a in sys.argv if a != "--q2"]
        from q2.main import main as q2_main

        q2_main()
    else:
        from q1.main import main as q1_main

        q1_main()


if __name__ == "__main__":
    main()
