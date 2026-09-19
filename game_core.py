# -*- coding: utf-8 -*-
"""
一箭又一箭 —— 核心游戏逻辑（纯 Python，不依赖任何图形库）

这样拆分的目的：
1. 界面（main.py）只负责画和收鼠标事件，规则判断全部集中在这里；
2. 自动化测试脚本（tools/autoplay_test.py）可以不用开窗口，
   直接 import 本模块模拟点击，验证每一关确实能通关。
"""

import random


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


# ---------------------------------------------------------------- 求解器与关卡生成
DIRS = list(DELTA.keys())

# 难度曲线：经典关卡与随机关卡共用（(行, 列, 箭头数, 失误上限, 开局至少被挡数, 主题名)）
LEVEL_CONFIGS = [
    (4, 4, 5, 3, 1, "初次上手"),
    (4, 4, 7, 3, 2, "两两相望"),
    (5, 5, 9, 3, 3, "十字路口"),
    (5, 5, 12, 4, 4, "箭阵"),
    (6, 6, 15, 4, 5, "一箭又一箭"),
]


def grid_from_specs(specs, rows, cols):
    """[(r,c,d), ...] -> ASCII 关卡文本"""
    g = [["." for _ in range(cols)] for _ in range(rows)]
    for (r, c, d) in specs:
        g[r][c] = DIR_2_SYMBOL[d]
    return ["".join(line) for line in g]


def _removable_in(state, rows, cols):
    """state 是 {(行,列,方向), ...}，返回其中当前能飞出棋盘的箭头。"""
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


def solve_state(state, rows, cols, memo=None):
    """DFS + 记忆化：在“剩余箭头集合”的状态空间里搜一条清空顺序，无解返回 None。"""
    memo = {} if memo is None else memo

    def dfs(st):
        if not st:
            return []
        if st in memo:
            return memo[st]
        for a in _removable_in(st, rows, cols):
            sub = dfs(st - {a})
            if sub is not None:
                memo[st] = [a] + sub
                return memo[st]
        memo[st] = None
        return None

    return dfs(state)


def solve_level(level, memo=None):
    """
    判断关卡是否可解，并返回一个可行的点击顺序（列表，元素为 (r,c,方向)）。
    解不出来返回 None。用于关卡生成与自动测试。
    """
    return solve_state(frozenset(level.arrow_specs()), level.rows, level.cols, memo)


def analyze_specs(specs, rows, cols, memo=None):
    """返回 (是否可解, 通关顺序, 开局被挡箭头数)"""
    state = frozenset(specs)
    memo = {} if memo is None else memo
    order = solve_state(state, rows, cols, memo)
    if order is None:
        return False, None, 0
    free = _removable_in(state, rows, cols)
    return True, order, len(state) - len(free)


def make_random_level(rows, cols, n_arrows, mistakes, min_blocked, rng,
                      name="随机关卡", max_tries=40000):
    """
    随机撒箭头，并**当场用求解器验证**：只接受“必定可通关、且开局至少有
    min_blocked 支箭头被挡住”的布局。找不到就放宽失败上限重试。
    返回 (Level, 求解器给出的通关顺序)。
    """
    cells = [(r, c) for r in range(rows) for c in range(cols)]
    memo = {}
    for attempt in range(max_tries):
        # 前半程严格要求阻挡数，避免个别配置搜不到时一直失败
        need = min_blocked if attempt < max_tries * 0.7 else max(1, min_blocked - 1)
        pick = rng.sample(cells, n_arrows)
        specs = [(r, c, rng.choice(DIRS)) for (r, c) in pick]
        ok, order, blocked = analyze_specs(specs, rows, cols, memo)
        if ok and blocked >= need:
            lv = Level(name, grid_from_specs(specs, rows, cols), mistakes,
                       cols=cols, rows=rows)
            return lv, order
    raise RuntimeError("生成关卡失败：%dx%d 箭头%d" % (rows, cols, n_arrows))


def build_run(seed=None, configs=None):
    """
    生成一整局的关卡列表（默认 5 关，难度按 LEVEL_CONFIGS 递进）。
    返回 (levels, seed)。同一个 seed 一定生成完全相同的关卡，便于复现。
    """
    if seed is None:
        seed = random.SystemRandom().randrange(1, 10 ** 9)
    rng = random.Random(seed)
    configs = LEVEL_CONFIGS if configs is None else configs
    levels = []
    for i, (rows, cols, n, mis, mb, theme) in enumerate(configs):
        lv, _order = make_random_level(
            rows, cols, n, mis, mb, rng,
            name="第%d关 · %s" % (i + 1, theme))
        levels.append(lv)
    return levels, seed


def find_hint(board):
    """给玩家用的提示：返回一个当前可以飞出的箭头（没有则返回 None）。"""
    cand = board.removable_arrows()
    return cand[0] if cand else None


# ---------------------------------------------------------------- 计分与星级
MAX_STARS = 3


def par_time(n_arrows, base=6.0, per_arrow=1.8):
    """
    本关目标时间（秒）：起步 6 秒 + 每支箭 1.8 秒。
    纯函数，只和箭头数量有关，便于测试与显示。
    """
    return base + per_arrow * n_arrows


def evaluate(elapsed, mistakes_used, n_arrows, max_mistakes=3):
    """
    结算一关的成绩。

    得分：基础 1000 分
        - 每次失误 -200
        - 超过目标时间后按超出比例最多再扣 250（避免“慢慢磨”也能满星）
        - 最低保底 100 分
    星级：
        3 星：零失误 且 用时不超过目标时间
        2 星：失误 ≤ 1 且 用时不超过目标时间的 1.6 倍
        1 星：通关即可
    返回 dict：score / stars / par / time_ratio / 明细字段
    """
    par = max(1e-6, par_time(n_arrows))
    ratio = elapsed / par
    overtime = max(0.0, ratio - 1.0)

    score = 1000 - 200 * mistakes_used - int(250 * min(1.0, overtime))
    score = max(100, int(score))

    if mistakes_used == 0 and ratio <= 1.0:
        stars = 3
    elif mistakes_used <= 1 and ratio <= 1.6:
        stars = 2
    else:
        stars = 1
    return {
        "score": score,
        "stars": stars,
        "par": par,
        "elapsed": elapsed,
        "time_ratio": ratio,
        "mistakes_used": mistakes_used,
        "max_mistakes": max_mistakes,
        "n_arrows": n_arrows,
    }
