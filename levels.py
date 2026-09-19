# -*- coding: utf-8 -*-
"""
经典关卡数据（由 tools/gen_levels.py 生成，全部通过求解器验证可通关）
符号：^ 上   v 下   < 左   > 右   . 空
说明：游戏默认使用「随机关卡模式」，每次开局现场生成并验证；
      这里的 5 关固定布局作为「经典关卡模式」保留。
"""

from game_core import Level  # noqa: F401

CLASSIC_LEVELS = [
    Level(
        name="第1关 · 初次上手",
        grid=[
            "....",
            "...v",
            "v...",
            ">v>.",
        ],
        mistakes=3,
    ),
    Level(
        name="第2关 · 两两相望",
        grid=[
            "v...",
            "..^.",
            "..<<",
            "<>.^",
        ],
        mistakes=3,
    ),
    Level(
        name="第3关 · 十字路口",
        grid=[
            "^>.>.",
            ".^v.>",
            ">>...",
            "..v..",
            ".....",
        ],
        mistakes=3,
    ),
    Level(
        name="第4关 · 箭阵",
        grid=[
            "^^.>.",
            "...<.",
            "^>^v.",
            "^..<.",
            "^..>.",
        ],
        mistakes=4,
    ),
    Level(
        name="第5关 · 一箭又一箭",
        grid=[
            "<...<>",
            "..^.<.",
            "..^..<",
            "...^v>",
            "..<>..",
            "v<...>",
        ],
        mistakes=4,
    ),
]

# 兼容旧引用
LEVELS = CLASSIC_LEVELS
