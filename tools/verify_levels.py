# -*- coding: utf-8 -*-
"""
关卡复核脚本：重新验证 levels.py 里的每一关都存在通关顺序，并打印一条解法。
交作业前跑一遍，作为“每个关卡都验证过可通关”的依据。

用法：
    python tools/verify_levels.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game_core import solve_level, DIR_2_SYMBOL  # noqa: E402
from levels import LEVELS  # noqa: E402


def main():
    all_ok = True
    for i, lv in enumerate(LEVELS):
        order = solve_level(lv)
        n = len(lv.arrow_specs())
        if order is None:
            print("第 %d 关  不可解 ✘" % (i + 1))
            all_ok = False
            continue
        print("第 %d 关  %dx%d  箭头 %d 支  失误上限 %d  可解 ✔"
              % (i + 1, lv.rows, lv.cols, n, lv.mistakes))
        print("        通关顺序：%s"
              % " -> ".join("%s(%d,%d)" % (DIR_2_SYMBOL[d], r, c) for (r, c, d) in order))
    print("\n结论：%s" % ("全部关卡可通关" if all_ok else "存在不可解关卡，请重新生成"))
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
