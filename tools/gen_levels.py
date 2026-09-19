# -*- coding: utf-8 -*-
"""
经典关卡生成 / 校验工具（开发期使用，游戏运行不需要它）

用法：
    python tools/gen_levels.py

随机撒箭头 -> 用求解器验证「一定存在通关顺序」-> 统计开局被挡箭头数，
挑选出难度递进的 5 个关卡，写成 levels.py 里的 CLASSIC_LEVELS。
生成逻辑复用 game_core.make_random_level()，和游戏内“随机关卡”用的是同一套代码。

注意：游戏运行时每次开局也会随机生成一套关卡（main.py 的随机模式），
      本脚本只是把一套固定的经典布局固化下来，便于评分时对照。

顺带说明一个求解器发现的游戏性质：
    箭头减少只会解除阻挡、不会制造新的阻挡（阻挡关系对“剩余箭头集合”单调），
    因此“每次都点当前能飞的箭头”一定能通关，不存在点错顺序导致的死局；
    关卡难度只能靠棋盘密度（开局被挡箭头数）来递进。
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game_core import (Level, LEVEL_CONFIGS, DIR_2_SYMBOL,  # noqa: E402
                       make_random_level, analyze_specs)


def main():
    out = []
    out.append("# -*- coding: utf-8 -*-\n")
    out.append('"""\n经典关卡数据（由 tools/gen_levels.py 生成，全部通过求解器验证可通关）\n')
    out.append("符号：^ 上   v 下   < 左   > 右   . 空\n")
    out.append("说明：游戏默认使用「随机关卡模式」，每次开局现场生成并验证；\n")
    out.append("      这里的 5 关固定布局作为「经典关卡模式」保留。\n\"\"\"\n\n")
    out.append("from game_core import Level  # noqa: F401\n\n")
    out.append("CLASSIC_LEVELS = [\n")

    for i, (rows, cols, n, mis, mb, theme) in enumerate(LEVEL_CONFIGS):
        seed = 11 + i * 137          # 固定种子 -> 每次生成结果一致
        rng = random.Random(seed)
        lv, order = make_random_level(
            rows, cols, n, mis, mb, rng,
            name="第%d关 · %s" % (i + 1, theme))
        _ok, _order, blocked = analyze_specs(lv.arrow_specs(), lv.rows, lv.cols)
        print("第 %d 关 %dx%d 箭头%d 开局被挡%d 失误上限%d"
              % (i + 1, rows, cols, n, blocked, mis))
        print("   一条通关顺序：%s"
              % " -> ".join("%s(%d,%d)" % (DIR_2_SYMBOL[d], r, c) for (r, c, d) in order))
        out.append("    Level(\n")
        out.append('        name="%s",\n' % lv.name)
        out.append("        grid=[\n")
        for line in lv.grid:
            out.append('            "%s",\n' % line)
        out.append("        ],\n")
        out.append("        mistakes=%d,\n" % mis)
        out.append("    ),\n")
    out.append("]\n\n")
    out.append("# 兼容旧引用\nLEVELS = CLASSIC_LEVELS\n")

    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "levels.py")
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(out)
    print("\n已写出 %s" % path)


if __name__ == "__main__":
    main()
