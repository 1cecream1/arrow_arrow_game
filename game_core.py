# -*- coding: utf-8 -*-
"""
一箭又一箭 —— 核心游戏逻辑（纯 Python，不依赖任何图形库）

这样拆分的目的：
1. 界面（main.py）只负责画和收鼠标事件，规则判断全部集中在这里；
2. 自动化测试脚本（tools/autoplay_test.py）可以不用开窗口，
   直接 import 本模块模拟点击，验证每一关确实能通关。
"""

UP = "U"
DOWN = "D"
LEFT = "L"
RIGHT = "R"

# 每个方向对应的行列增量
DELTA = {
    UP: (-1, 0),
    DOWN: (1, 0),
    LEFT: (0, -1),
    RIGHT: (0, 1),
}

# 关卡用 ASCII 字符书写，方便人读人改
SYMBOL_2_DIR = {"^": UP, "v": DOWN, "<": LEFT, ">": RIGHT}
DIR_2_SYMBOL = {v: k for k, v in SYMBOL_2_DIR.items()}

DIR_NAME_CN = {UP: "上", DOWN: "下", LEFT: "左", RIGHT: "右"}


class Arrow:
    """棋盘上的一个单格箭头。"""

    __slots__ = ("r", "c", "d", "uid")

    def __init__(self, r, c, d, uid):
        self.r = r          # 行号（0 开始，从上往下）
        self.c = c          # 列号（0 开始，从左往右）
        self.d = d          # 方向：U / D / L / R
        self.uid = uid      # 唯一编号，界面动画需要跟踪同一个箭头

    def key(self):
        return (self.r, self.c, self.d)

    def __repr__(self):
        return "Arrow(%d,%d,%s)" % (self.r, self.c, self.d)


class Level:
    """一个关卡的定义。"""

    def __init__(self, name, grid, mistakes, cols=None, rows=None):
        self.name = name
        self.grid = grid                      # 字符串列表，例如 ["..>.", "..^."]
        self.rows = rows if rows else len(grid)
        self.cols = cols if cols else len(grid[0])
        self.mistakes = mistakes              # 本关允许的失误次数

    def arrow_specs(self):
        """把 ASCII 关卡翻译成 [(行, 列, 方向), ...]"""
        specs = []
        for r, line in enumerate(self.grid):
            for c, ch in enumerate(line):
                if ch in SYMBOL_2_DIR:
                    specs.append((r, c, SYMBOL_2_DIR[ch]))
        return specs


def parse_grid(grid):
    """工具函数：ASCII 关卡 -> 箭头三元组列表"""
    return Level("tmp", grid).arrow_specs()


class Board:
    """一局游戏的棋盘状态。"""

    def __init__(self, level):
        self.level = level
        self.rows = level.rows
        self.cols = level.cols
        self.max_mistakes = level.mistakes
        self.mistakes_left = level.mistakes
        self.arrows = []
        self._uid = 0
        for (r, c, d) in level.arrow_specs():
            self.arrows.append(Arrow(r, c, d, self._uid))
            self._uid += 1
        self.removed_count = 0
        self.click_count = 0

    # ---------- 查询 ----------
    def alive_arrows(self):
        return [a for a in self.arrows if a is not None]

    def remaining(self):
        return len(self.alive_arrows())

    def total(self):
        return len(self.arrows)

    def arrow_at(self, r, c):
        for a in self.arrows:
            if a is not None and a.r == r and a.c == c:
                return a
        return None

    def scan(self, arrow):
        """
        检查 arrow 前进方向到边界之间有没有别的箭头。
        返回 (是否通畅, 挡路的箭头 or None)
        规则：同一行 / 同一列，从箭头的下一格一路走到棋盘外。
        """
        dr, dc = DELTA[arrow.d]
        r, c = arrow.r + dr, arrow.c + dc
        while 0 <= r < self.rows and 0 <= c < self.cols:
            other = self.arrow_at(r, c)
            if other is not None:
                return False, other
            r += dr
            c += dc
        return True, None

    def is_removable(self, arrow):
        clear, _ = self.scan(arrow)
        return clear

    def removable_arrows(self):
        return [a for a in self.alive_arrows() if self.is_removable(a)]

    def blocked_arrows(self):
        return [a for a in self.alive_arrows() if not self.is_removable(a)]

    # ---------- 操作 ----------
    def click(self, arrow):
        """
        玩家点击某个箭头。
        返回字典：
          {'ok': True,  'result': 'fly',     'arrow': a}                      可飞出
          {'ok': False, 'result': 'blocked', 'arrow': a, 'blocker': b,
           'fail': bool}                                                       被挡住
        """
        if arrow is None or arrow not in self.arrows:
            return {"ok": False, "result": "none"}
        self.click_count += 1
        clear, blocker = self.scan(arrow)
        if clear:
            return {"ok": True, "result": "fly", "arrow": arrow}
        self.mistakes_left -= 1
        return {
            "ok": False,
            "result": "blocked",
            "arrow": arrow,
            "blocker": blocker,
            "mistakes_left": self.mistakes_left,
            "fail": self.mistakes_left <= 0,
        }

    def remove(self, arrow):
        """把箭头真正从棋盘上抹掉（在飞出动画结束后调用）。"""
        for i, a in enumerate(self.arrows):
            if a is arrow:
                self.arrows[i] = None
                self.removed_count += 1
                return True
        return False

    def is_cleared(self):
        return self.remaining() == 0

    def reset(self):
        self.__init__(self.level)


# ---------------------------------------------------------------- 求解器
def solve_level(level, _memo=None):
    """
    判断关卡是否可解，并返回一个可行的点击顺序（列表，元素为 (r,c,方向)）。
    解不出来返回 None。用于关卡生成与自动测试。
    思路：DFS + 记忆化，状态为剩余箭头的集合。
    """
    rows, cols = level.rows, level.cols
    state = frozenset(level.arrow_specs())
    memo = {} if _memo is None else _memo

    def removable(st):
        occ = {(r, c) for (r, c, _) in st}
        out = []
        for a in st:
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

    def dfs(st):
        if not st:
            return []
        if st in memo:
            return memo[st]
        for a in removable(st):
            sub = dfs(st - {a})
            if sub is not None:
                memo[st] = [a] + sub
                return memo[st]
        memo[st] = None
        return None

    return dfs(state)


def find_hint(board):
    """给玩家用的提示：返回一个当前可以飞出的箭头（没有则返回 None）。"""
    cand = board.removable_arrows()
    return cand[0] if cand else None
