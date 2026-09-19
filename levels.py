# -*- coding: utf-8 -*-
"""
关卡数据（由 tools/gen_levels.py 自动生成，全部通过求解器验证可通关）
符号：^ 上   v 下   < 左   > 右   . 空
"""

from game_core import Level  # noqa: F401

LEVELS = [
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
            ".v.>",
            "<...",
            "..v<",
            ".<.<",
        ],
        mistakes=3,
    ),
    Level(
        name="第3关 · 十字路口",
        grid=[
            ".....",
            "<<..<",
            "^.<..",
            "..>.^",
            "v.v..",
        ],
        mistakes=3,
    ),
    Level(
        name="第4关 · 箭阵",
        grid=[
            ".^<<.",
            "^.^..",
            "...<>",
            "..v.^",
            ".^<.>",
        ],
        mistakes=4,
    ),
    Level(
        name="第5关 · 一箭又一箭",
        grid=[
            "^.....",
            "..^^v.",
            ">.>..^",
            "<..^<<",
            "v...v.",
            "v....v",
        ],
        mistakes=4,
    ),
]
