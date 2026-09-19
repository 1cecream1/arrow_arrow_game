# -*- coding: utf-8 -*-
"""
关卡生成 / 校验工具（开发期使用，游戏运行不需要它）

用法：
    python tools/gen_levels.py

作用：随机撒箭头 -> 用 DFS 求解器验证「一定存在通关顺序」-> 统计开局被挡箭头数，
      挑选出难度递进的 5 个关卡，并写成 levels.py。

顺带说明一个求解器发现的游戏性质：
    箭头减少只会解除阻挡、不会制造新的阻挡（阻挡关系对“剩余箭头集合”单调），
    因此“每次都点当前能飞的箭头”一定能通关，不存在点错顺序导致的死局；
    关卡难度只能靠棋盘密度（开局被挡箭头数）来递进。
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game_core import Level, DELTA, DIR_2_SYMBOL  # noqa: E402

DIRS = list(DELTA.keys())


def to_grid(specs, rows, cols):
    g = [["." for _ in range(cols)] for _ in range(rows)]
    for (r, c, d) in specs:
        g[r][c] = DIR_2_SYMBOL[d]
    return ["".join(line) for line in g]


def removable_in(state, rows, cols):
    occ = {(r, c) for (r, c, _) in state}
    out = []
    for a in state:
        r, c, d = a
        dr, dc = DELTA[d]
        r += dr
        c += dc
        ok = True
        while 0 <= r < rows and 0 <= c < cols:
            if (r, c) in occ:
                ok = False
                break
            r += dr
            c += dc
        if ok:
            out.append(a)
    return out


def solve(state, rows, cols, memo):
    if not state:
        return []
    if state in memo:
        return memo[state]
    for a in removable_in(state, rows, cols):
        sub = solve(state - {a}, rows, cols, memo)
        if sub is not None:
            memo[state] = [a] + sub
            return memo[state]
    memo[state] = None
    return None


def analyse(specs, rows, cols):
    """返回 (是否可解, 通关顺序, 开局被挡箭头数)"""
    state = frozenset(specs)
    memo = {}
    order = solve(state, rows, cols, memo)
    if order is None:
        return False, None, 0
    free = removable_in(state, rows, cols)
    blocked = len(state) - len(free)
    return True, order, blocked


def make_level(idx, rows, cols, n_arrow, mistakes, min_blocked, seed):
    random.seed(seed)
    cells = [(r, c) for r in range(rows) for c in range(cols)]
    for _ in range(60000):
        pick = random.sample(cells, n_arrow)
        specs = [(r, c, random.choice(DIRS)) for (r, c) in pick]
        ok, order, blocked = analyse(specs, rows, cols)
        if ok and blocked >= min_blocked:
            return to_grid(specs, rows, cols), order, blocked
    raise RuntimeError("level %d 生成失败，请放宽条件" % idx)


CONFIGS = [
    # (行, 列, 箭头数, 失误上限, 开局至少被挡数, 随机种子)
    (4, 4, 5, 3, 1, 11),
    (4, 4, 7, 3, 2, 27),
    (5, 5, 9, 3, 3, 5),
    (5, 5, 12, 4, 4, 13),
    (6, 6, 15, 4, 5, 41),
]

LEVEL_NAMES = ["初次上手", "两两相望", "十字路口", "箭阵", "一箭又一箭"]


def main():
    out = []
    out.append("# -*- coding: utf-8 -*-\n")
    out.append('"""\n关卡数据（由 tools/gen_levels.py 自动生成，全部通过求解器验证可通关）\n')
    out.append("符号：^ 上   v 下   < 左   > 右   . 空\n\"\"\"\n\n")
    out.append("from game_core import Level  # noqa: F401\n\n")
    out.append("LEVELS = [\n")

    for i, (rows, cols, n, mis, mb, seed) in enumerate(CONFIGS):
        grid, order, blocked = make_level(i, rows, cols, n, mis, mb, seed)
        print("第 %d 关 %dx%d 箭头%d 开局被挡%d 失误上限%d"
              % (i + 1, rows, cols, n, blocked, mis))
        print("   一条通关顺序：%s"
              % " -> ".join("%s(%d,%d)" % (DIR_2_SYMBOL[d], r, c) for (r, c, d) in order))
        out.append("    Level(\n")
        out.append('        name="第%d关 · %s",\n' % (i + 1, LEVEL_NAMES[i]))
        out.append("        grid=[\n")
        for line in grid:
            out.append('            "%s",\n' % line)
        out.append("        ],\n")
        out.append("        mistakes=%d,\n" % mis)
        out.append("    ),\n")
    out.append("]\n")

    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "levels.py")
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(out)
    print("\n已写出 %s" % path)


if __name__ == "__main__":
    main()
