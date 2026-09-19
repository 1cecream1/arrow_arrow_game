# -*- coding: utf-8 -*-
"""
一箭又一箭 —— Pygame 图形界面与主循环

玩法：
    点击棋盘上的箭头。如果它前进方向到棋盘边界之间没有其他箭头，
    它就沿该方向飞出棋盘并消失；否则视为一次失误（箭头晃动变红提示碰撞），
    失误次数耗尽则本关失败。清空全部箭头进入下一关。

运行：
    python main.py
"""
import json
import math
import os
import random
import sys

import pygame

from game_core import (Board, DELTA, DIR_NAME_CN, find_hint, build_run,
                       make_random_level, evaluate, par_time, MAX_STARS)
from levels import CLASSIC_LEVELS
from sprites import sprites, draw_arrow_proc, draw_heart_proc
from sound import sound

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RECORDS_PATH = os.path.join(BASE_DIR, "records.json")

# ------------------------------------------------------------------ 基本参数
WIN_W, WIN_H = 960, 720
FPS = 60

# 浅色主题配色
C_BG = (245, 247, 250)
C_PANEL = (255, 255, 255)
C_TEXT = (43, 51, 65)
C_TEXT_SUB = (120, 130, 145)
C_GRID = (216, 223, 232)
C_BOARD_BG = (255, 255, 255)
C_BOARD_EDGE = (58, 79, 106)
C_ARROW = (44, 107, 209)          # 正常箭头：蓝
C_RED = (225, 70, 75)             # 碰撞 / 失误：红
C_GREEN = (46, 160, 95)           # 可飞出提示：绿
C_BTN = (44, 107, 209)
C_BTN_HOVER = (62, 128, 232)
C_BTN_TEXT = (255, 255, 255)

# 菜单布局（左侧规则卡片 / 右侧自动演示卡片）
MENU_RULES_RECT = pygame.Rect(60, 158, 600, 258)
MENU_DEMO_CARD = pygame.Rect(686, 158, 214, 258)
MENU_DEMO_RECT = pygame.Rect(705, 206, 176, 176)

# 关卡选项界面：5 张关卡卡片（尺寸统一，间距一致）
LEVEL_CARD_W, LEVEL_CARD_H, LEVEL_CARD_GAP = 168, 250, 15
LEVEL_CARD_Y = 150


def level_card_rect(i):
    total = 5 * LEVEL_CARD_W + 4 * LEVEL_CARD_GAP
    x0 = (WIN_W - total) // 2
    return pygame.Rect(x0 + i * (LEVEL_CARD_W + LEVEL_CARD_GAP), LEVEL_CARD_Y,
                       LEVEL_CARD_W, LEVEL_CARD_H)


# ------------------------------------------------------------------ 星级
_star_cache = {}


def star_image(size, filled):
    """五角星（程序绘制，避免再多生成图片素材）；按 (尺寸, 点亮) 缓存。"""
    key = (size, filled)
    if key in _star_cache:
        return _star_cache[key]
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    cx = cy = size / 2
    R, r = size * 0.5, size * 0.5 * 0.44
    pts = []
    for k in range(10):
        ang = -math.pi / 2 + k * math.pi / 5
        rad = R if k % 2 == 0 else r
        pts.append((cx + math.cos(ang) * rad, cy + math.sin(ang) * rad))
    if filled:
        body, edge, shine = (247, 181, 25), (196, 132, 8), (255, 226, 138)
    else:
        body, edge, shine = (223, 228, 236), (203, 209, 219), (238, 241, 245)
    pygame.draw.polygon(surf, body, pts)
    pygame.draw.polygon(surf, edge, pts, max(1, int(size * 0.045)))
    # 上半部分画一颗小一点的浅色星，做出一点立体高光
    inner = []
    for k in range(10):
        ang = -math.pi / 2 + k * math.pi / 5
        rad = (R if k % 2 == 0 else r) * 0.58
        inner.append((cx + math.cos(ang) * rad, cy + math.sin(ang) * rad - size * 0.09))
    pygame.draw.polygon(surf, shine, inner)
    _star_cache[key] = surf
    return surf


def draw_star(surface, cx, cy, size, filled=True, scale=1.0):
    """按中心点绘制星星；scale 用于出现动画。"""
    s = max(1, int(size * scale))
    img = star_image(s, filled)
    surface.blit(img, (int(cx - s / 2), int(cy - s / 2)))


def draw_star_row(surface, cx, cy, size, stars, gap=None, progress=None):
    """
    画一排 3 颗星：点亮的星按 progress 逐颗弹出；没点亮的星一直是暗色底星
    （保证任何时候都能看出“这关最多 3 星、我拿了几颗”）。
    """
    gap = size * 1.28 if gap is None else gap
    total = MAX_STARS * size + (MAX_STARS - 1) * (gap - size)
    x = cx - total / 2 + size / 2
    for i in range(MAX_STARS):
        filled = i < stars
        scale = 1.0
        if filled and progress is not None:
            p = max(0.0, min(1.0, (progress - i * 0.15) / 0.26))
            scale = _ease_out_back(p) if p > 0 else 0.001
        if filled and scale <= 0.001:
            pass                     # 还没轮到它出现
        else:
            draw_star(surface, x, cy, size, filled=filled, scale=scale)
        x += gap


def _ease_out_back(x, c1=1.70158, c3=2.70158):
    """回弹缓动：星星弹出来会稍微过冲一下，比较有“得分感”。"""
    x -= 1.0
    return 1 + c3 * x ** 3 + c1 * x ** 2


# ------------------------------------------------------------------ 成绩记录
def load_records(path):
    """读取本地最高分记录（不存在或损坏时返回空记录，不影响游戏）。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("levels"), dict):
            return data
    except (OSError, ValueError):
        pass
    return {"version": 1, "levels": {}}


def save_records(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False


# ------------------------------------------------------------------ 箭头 / 爱心
C_HUD = (233, 238, 245)

# ------------------------------------------------------------------ 字体
_FONT_DIR = "C:/Windows/Fonts"


def get_font(size, bold=False):
    """中文字体：优先微软雅黑，失败则退回系统字体。"""
    candidates = [
        os.path.join(_FONT_DIR, "msyhbd.ttc" if bold else "msyh.ttc"),
        os.path.join(_FONT_DIR, "simhei.ttf"),
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                return pygame.font.Font(p, size)
            except Exception:
                pass
    return pygame.font.SysFont("microsoftyahei, simhei, sans", size, bold=bold)


# ------------------------------------------------------------------ 箭头 / 爱心
# 优先使用 AIGC 生成的图片素材（sprites），素材缺失时退回程序绘制。
def draw_arrow(surface, cx, cy, size, direction, color=C_ARROW):
    """在 (cx, cy) 为中心、边长 size 处画出指向 direction 的箭头。"""
    img = sprites.arrow(direction, size)
    if img is not None:
        surface.blit(img, img.get_rect(center=(int(cx), int(cy))))
        return
    draw_arrow_proc(surface, cx, cy, size, direction, color)


def draw_heart(surface, cx, cy, size, filled=True):
    """剩余失误用的爱心：filled=True 满心，False 表示已消耗。"""
    img = sprites.heart(size) if filled else sprites.heart_empty(size)
    if img is not None:
        surface.blit(img, img.get_rect(center=(int(cx), int(cy))))
        return
    draw_heart_proc(surface, cx, cy, size, C_RED if filled else (205, 210, 218))


def lerp_color(c1, c2, t):
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


# ------------------------------------------------------------------ 动画对象
class ArrowView:
    """负责一个箭头的渲染状态：正常 / 晃动+闪红（碰撞）/ 飞出 / 提示高亮。"""

    def __init__(self, arrow, cell_center):
        self.arrow = arrow
        self.cx, self.cy = cell_center
        self.state = "idle"          # idle / fly / dead
        self.px = 0.0                # 像素偏移
        self.py = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.shake_t = 0.0           # 碰撞晃动剩余时间
        self.flash_t = 0.0           # 碰撞闪红剩余时间
        self.hint_t = 0.0            # 提示高亮剩余时间
        self.alive_visual = True     # 飞出动画播完后再消失

    def update(self, dt, board_rect):
        if self.shake_t > 0:
            self.shake_t = max(0.0, self.shake_t - dt)
        if self.flash_t > 0:
            self.flash_t = max(0.0, self.flash_t - dt)
        if self.hint_t > 0:
            self.hint_t = max(0.0, self.hint_t - dt)

        if self.state == "fly":
            # 加速飞出
            self.vx *= 1.0 + 2.5 * dt
            self.vy *= 1.0 + 2.5 * dt
            self.px += self.vx * dt
            self.py += self.vy * dt
            x, y = self.cx + self.px, self.cy + self.py
            margin = 120
            if (x < board_rect.x - margin or x > board_rect.right + margin
                    or y < board_rect.y - margin or y > board_rect.bottom + margin):
                self.state = "dead"
                self.alive_visual = False

    def draw(self, surface, cell):
        if not self.alive_visual:
            return
        ox, oy = self.px, self.py
        if self.shake_t > 0:
            # 垂直于箭头方向左右晃
            dx, dy = DELTA[self.arrow.d]
            amp = 8.0 * (self.shake_t / 0.45)
            off = math.sin(self.shake_t * 55) * amp
            ox += -dy * off
            oy += dx * off

        cx, cy = self.cx + ox, self.cy + oy
        img = sprites.arrow(self.arrow.d, cell)
        if img is not None:
            surface.blit(img, img.get_rect(center=(int(cx), int(cy))))
            if self.flash_t > 0:
                # 红色版本按剩余时间淡入淡出 -> 颜色平滑过渡，不是硬切
                fl = sprites.arrow_flash(self.arrow.d, cell)
                if fl is not None:
                    ratio = min(1.0, self.flash_t / 0.45)
                    fl.set_alpha(int(250 * ratio))     # 峰值几乎全红，之后线性淡出
                    surface.blit(fl, fl.get_rect(center=(int(cx), int(cy))))
        else:
            color = C_ARROW
            if self.flash_t > 0:
                color = lerp_color(C_ARROW, C_RED, min(1.0, self.flash_t / 0.45 * 1.4))
            draw_arrow_proc(surface, cx, cy, cell, self.arrow.d, color)

        if self.hint_t > 0:
            a = int(140 * min(1.0, self.hint_t))
            r = pygame.Rect(0, 0, cell * 0.9, cell * 0.9)
            r.center = (int(self.cx + ox), int(self.cy + oy))
            ring = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
            pygame.draw.rect(ring, (C_GREEN[0], C_GREEN[1], C_GREEN[2], a), r, 6, border_radius=10)
            surface.blit(ring, r.topleft)


class FloatText:
    """碰撞 / 提示时的漂浮文字。"""

    def __init__(self, text, x, y, color, size=30, life=1.0):
        self.text = text
        self.x, self.y = x, y
        self.color = color
        self.life = life
        self.age = 0.0
        self.size = size
        self.font = get_font(size, bold=True)

    def update(self, dt):
        self.age += dt
        return self.age < self.life

    def draw(self, surface):
        t = self.age / self.life
        a = int(255 * (1.0 - t))
        img = self.font.render(self.text, True, self.color)
        x = max(12, min(WIN_W - 12 - img.get_width(), self.x - img.get_width() / 2))
        y = max(120, self.y - 40 * t - img.get_height() / 2)
        # 半透明底衬，保证文字压在箭头上也看得清
        pad_x, pad_y = 12, 6
        pill = pygame.Surface((img.get_width() + pad_x * 2, img.get_height() + pad_y * 2),
                              pygame.SRCALPHA)
        pygame.draw.rect(pill, (255, 255, 255, min(215, a)),
                         pill.get_rect(), border_radius=12)
        pygame.draw.rect(pill, (*self.color, min(90, a)),
                         pill.get_rect(), 2, border_radius=12)
        surface.blit(pill, (x - pad_x, y - pad_y))
        img.set_alpha(a)
        surface.blit(img, (x, y))


class Ring:
    """箭头起飞 / 落点确认时的一圈涟漪。"""

    def __init__(self, x, y, color=C_ARROW, life=0.35):
        self.x, self.y = x, y
        self.color = color
        self.life = life
        self.age = 0.0

    def update(self, dt):
        self.age += dt
        return self.age < self.life

    def draw(self, surface, cell):
        t = self.age / self.life
        radius = cell * (0.3 + 0.8 * t)
        a = int(200 * (1 - t))
        if a > 0:
            s = pygame.Surface((radius * 2 + 4, radius * 2 + 4), pygame.SRCALPHA)
            pygame.draw.circle(s, (*self.color, a), (int(radius + 2), int(radius + 2)), int(radius), 4)
            surface.blit(s, (self.x - radius - 2, self.y - radius - 2))


# ------------------------------------------------------------------ 菜单演示
class MenuDemo:
    """
    菜单里的自动演示小棋盘：4×4、6 支箭，每次挑一个“当前能飞”的箭头飞出，
    清空后自动换一局。让玩家在进游戏前一眼看懂玩法。
    之所以敢随便挑一个能飞的箭头：箭头减少只会解除阻挡、不会制造阻挡，
    所以任何时刻点任何一个可飞的箭头都不会走进死局。
    """

    def __init__(self, rect):
        self.rect = pygame.Rect(rect)
        self.cell = self.rect.w // 4
        self.board = None
        self.views = []
        self.rings = []
        self.timer = 0.0
        self.new_round()

    def cell_center(self, r, c):
        return (self.rect.x + c * self.cell + self.cell / 2,
                self.rect.y + r * self.cell + self.cell / 2)

    def new_round(self):
        lv, _order = make_random_level(4, 4, 6, 3, 1, random.Random(), name="demo")
        self.board = Board(lv)
        self.views = [ArrowView(a, self.cell_center(a.r, a.c))
                      for a in self.board.alive_arrows()]
        self.rings = []
        self.timer = 0.7          # 新一局先停一下再动

    def update(self, dt):
        for v in self.views:
            v.update(dt, self.rect)
        if any(v.state == "dead" for v in self.views):
            self.views = [v for v in self.views if v.state != "dead"]
        self.rings = [rg for rg in self.rings if rg.update(dt)]

        if any(v.state == "fly" for v in self.views):
            return                       # 等这支飞完再出下一支
        self.timer -= dt
        if self.timer > 0:
            return
        if self.board.is_cleared():
            self.new_round()
            return
        cand = self.board.removable_arrows()
        if not cand:
            self.new_round()
            return
        a = random.choice(cand)
        self.board.remove(a)
        v = next((v for v in self.views if v.arrow is a), None)
        if v is None:
            return
        dr, dc = DELTA[a.d]
        v.state = "fly"
        v.vx = dc * 340.0
        v.vy = dr * 340.0
        self.rings.append(Ring(v.cx, v.cy))
        self.timer = 0.42                # 下一支的间隔

    def draw(self, surface):
        pygame.draw.rect(surface, C_BOARD_BG, self.rect, border_radius=10)
        pygame.draw.rect(surface, C_GRID, self.rect, 1, border_radius=10)
        for i in range(1, 4):
            x = self.rect.x + i * self.cell
            pygame.draw.line(surface, C_GRID, (x, self.rect.y + 2),
                             (x, self.rect.bottom - 2), 1)
            y = self.rect.y + i * self.cell
            pygame.draw.line(surface, C_GRID, (self.rect.x + 2, y),
                             (self.rect.right - 2, y), 1)
        for v in self.views:
            v.draw(surface, self.cell)
        for rg in self.rings:
            rg.draw(surface, self.cell)


class Button:
    def __init__(self, rect, text, font=None, normal=C_BTN, hover=C_BTN_HOVER, small=False):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.normal = normal
        self.hover = hover
        self.font = font or get_font(20 if small else 24, bold=True)
        self.hovered = False

    def update_hover(self, mouse):
        self.hovered = self.rect.collidepoint(mouse)
        return self.hovered

    def draw(self, surface):
        color = self.hover if self.hovered else self.normal
        r = self.rect.inflate(-4, -4)
        pygame.draw.rect(surface, color, r, border_radius=12)
        # 底部一条深色边，制造一点立体感
        pygame.draw.rect(surface, tuple(max(0, int(c * 0.8)) for c in color),
                         (r.x, r.bottom - 6, r.w, 6), border_radius=3)
        img = self.font.render(self.text, True, C_BTN_TEXT)
        surface.blit(img, (r.centerx - img.get_width() // 2, r.centery - img.get_height() // 2))

    def hit(self, pos):
        return self.rect.collidepoint(pos)


# ------------------------------------------------------------------ 游戏
class Game:
    STATE_MENU = "menu"
    STATE_LEVELS = "levels"          # 关卡选项（更多关卡）
    STATE_PLAY = "play"
    STATE_CLEAR = "clear"            # 本关通关（过渡）
    STATE_FAIL = "fail"
    STATE_ALLCLEAR = "allclear"

    def __init__(self, headless=False, mode="classic", seed=None, records_path=None):
        if headless:
            os.environ.setdefault("SDL_VIDEODRIVER", "dummy")   # 自动测试/截图用
        pygame.init()
        pygame.display.set_caption("一箭又一箭")
        self.screen = pygame.display.set_mode((WIN_W, WIN_H))
        self.clock = pygame.time.Clock()
        self.running = True
        self.headless = headless
        sprites.preload()            # 显示初始化后加载 AIGC 素材（缺失则自动兜底）
        sound.preload()              # 音效（没有声卡/素材时自动静默降级）

        self.font_title = get_font(64, bold=True)
        self.font_big = get_font(44, bold=True)
        self.font_mid = get_font(28, bold=True)
        self.font_small = get_font(20)
        self.font_tiny = get_font(17)
        self.font_hud = get_font(24, bold=True)

        self.level_index = 0
        self.total_mistakes = 0      # 全程失误统计（全部通关界面展示）
        self.state = self.STATE_MENU
        self.views = []              # ArrowView 列表
        self.floats = []             # 漂浮文字
        self.rings = []
        self.clear_wait = 0.0        # 清空后等最后一支箭飞完
        self.fail_wait = 0.0

        # 计分 / 星级 / 记录
        self.elapsed = 0.0           # 本关用时（只在游戏进行中累加，看结算界面不计时）
        self.run_score = 0           # 本局累计得分
        self.result = None           # 本关结算结果（evaluate 的返回值）
        self.clear_anim = 0.0        # 通关弹窗里的星星出现动画进度
        self.records_path = records_path or RECORDS_PATH
        self.records = load_records(self.records_path)

        # 本局的关卡列表：随机模式现场生成，经典模式用固定布局
        self.mode = mode
        self.run_seed = None
        self.levels = []

        # 各界面按钮（尺寸与原来保持一致）
        self.btn_start = Button((WIN_W / 2 - 200, 452, 400, 62), "开 始 游 戏")
        self.btn_more = Button((WIN_W / 2 - 200, 528, 400, 52), "更多关卡（共 %d 关）"
                               % len(CLASSIC_LEVELS), small=True, normal=(126, 136, 152))
        self.btn_random = Button((WIN_W / 2 + 20, 576, 200, 58), "随机挑战")
        self.btn_back_lv = Button((WIN_W / 2 - 220, 576, 200, 58), "返回菜单")
        self.btn_restart = Button((70, WIN_H - 78, 170, 54), "重新开始")
        self.btn_hint = Button((260, WIN_H - 78, 170, 54), "提示一下")
        self.btn_menu = Button((450, WIN_H - 78, 170, 54), "返回菜单")
        self.btn_next = Button((WIN_W / 2 - 220, 398, 200, 58), "下一关 →")
        self.btn_retry = Button((WIN_W / 2 - 220, 398, 200, 58), "重新挑战")
        self.btn_back2 = Button((WIN_W / 2 + 20, 398, 200, 58), "关卡选项")
        self.btn_again = Button((WIN_W / 2 - 110, 500, 220, 60), "再来一遍")

        # 菜单里的自动演示棋盘
        self.demo = MenuDemo(MENU_DEMO_RECT)
        self._menu_layer = None      # 菜单静态层缓存（首帧渲染一次）
        self._lv_layer = None        # 关卡选项静态层缓存（成绩变化时重建）

        self.new_run(mode, seed)
        self.state = self.STATE_MENU      # 开机先进菜单

    # ------------------------------------------------ 关卡 / 棋盘
    def new_run(self, mode=None, seed=None):
        """
        开一局。随机模式：现场生成 5 关，每关都由求解器验证「一定可通关」；
        经典模式：使用 levels.py 里固定的 5 关（关卡选项里可直接挑战某一关）。
        同一个 seed 生成的布局完全相同。
        """
        if mode is not None:
            self.mode = mode
        if self.mode == "classic":
            self.levels = list(CLASSIC_LEVELS)
            self.run_seed = None
        else:
            self.levels, self.run_seed = build_run(seed)
        self.total_mistakes = 0
        self.run_score = 0
        self.start_level(0)

    def start_level(self, idx):
        self.level_index = idx
        self.board = Board(self.levels[idx])
        self._layout()
        self.state = self.STATE_PLAY
        self.floats.clear()
        self.rings.clear()
        self.clear_wait = 0.0
        self.fail_wait = 0.0
        self.elapsed = 0.0          # 本关用时重新计时
        self.result = None          # 本关结算结果清空
        self.clear_anim = 0.0
        self._sync_views()

    def par_of_level(self, idx):
        """本关目标时间：按箭头数量算（纯函数，见 game_core.par_time）。"""
        return par_time(len(self.levels[idx].arrow_specs()))

    def best_of_level(self, idx):
        """本地最佳成绩记录（仅经典关卡有意义，随机关卡布局不同不记录）。"""
        return self.records.get("levels", {}).get(str(idx))

    def commit_result(self):
        """本关清空后结算：算分、给星、累计总分、刷新本地最佳记录。"""
        total = len(self.levels[self.level_index].arrow_specs())
        used = self.board.max_mistakes - self.board.mistakes_left
        self.result = evaluate(self.elapsed, used, total, self.board.max_mistakes)
        self.run_score += self.result["score"]
        self.result["new_record"] = False
        if self.mode == "classic":
            key = str(self.level_index)
            old = self.records.setdefault("levels", {}).get(key)
            if old is None or self.result["score"] > old.get("score", -1):
                self.records["levels"][key] = {
                    "score": self.result["score"],
                    "stars": self.result["stars"],
                    "best_time": round(self.result["elapsed"], 2),
                    "mistakes": used,
                }
                save_records(self.records_path, self.records)
                self.result["new_record"] = True
                self._lv_layer = None       # 成绩变了，关卡选项的静态层要重建
                return True
        return False

    def restart_level(self):
        self.start_level(self.level_index)

    def _layout(self):
        """根据行列数计算棋盘像素位置与格子大小。"""
        rows, cols = self.board.rows, self.board.cols
        area = pygame.Rect(70, 140, WIN_W - 140, WIN_H - 240)
        cell = min(area.w // cols, area.h // rows)
        cell = max(44, min(cell, 96))
        bw, bh = cell * cols, cell * rows
        self.cell = cell
        self.board_rect = pygame.Rect(WIN_W // 2 - bw // 2,
                                      area.y + (area.h - bh) // 2, bw, bh)

    def cell_center(self, r, c):
        b = self.board_rect
        return (b.x + c * self.cell + self.cell / 2,
                b.y + r * self.cell + self.cell / 2)

    def _sync_views(self):
        self.views = [ArrowView(a, self.cell_center(a.r, a.c))
                      for a in self.board.alive_arrows()]

    def view_of(self, arrow):
        for v in self.views:
            if v.arrow is arrow:
                return v
        return None

    # ------------------------------------------------ 交互
    def on_click(self, pos):
        """统一处理一次点击（鼠标事件与自动化测试共用这条路）。"""
        if self.state == self.STATE_MENU:
            if self.btn_start.hit(pos):
                self.new_run("classic")          # 开始游戏 = 经典 5 关
            elif self.btn_more.hit(pos):
                self.state = self.STATE_LEVELS   # 更多关卡 = 关卡选项
            return

        if self.state == self.STATE_LEVELS:
            if self.btn_back_lv.hit(pos):
                self.state = self.STATE_MENU
                return
            if self.btn_random.hit(pos):
                self.new_run("random")           # 随机挑战：现场生成 5 关
                return
            for i in range(len(CLASSIC_LEVELS)):
                if level_card_rect(i).collidepoint(pos):
                    self.new_run("classic")      # 从选中的那关开始
                    self.start_level(i)
                    return
            return

        if self.state == self.STATE_PLAY:
            if self.btn_restart.hit(pos):
                self.restart_level()
                return
            if self.btn_hint.hit(pos):
                self.do_hint()
                return
            if self.btn_menu.hit(pos):
                self.state = self.STATE_MENU
                return
            self.click_board(pos)
            return

        if self.state == self.STATE_CLEAR:
            if self.btn_next.hit(pos):
                self.start_level(self.level_index + 1)
            elif self.btn_back2.hit(pos):
                self.state = self.STATE_LEVELS    # 回关卡选项，接着挑关打
            return

        if self.state == self.STATE_FAIL:
            if self.btn_retry.hit(pos):
                self.start_level(self.level_index)
            elif self.btn_back2.hit(pos):
                self.state = self.STATE_LEVELS
            return

        if self.state == self.STATE_ALLCLEAR:
            if self.btn_again.hit(pos):
                self.new_run(self.mode)         # 换一批新关卡再来
            return

    def click_board(self, pos):
        b = self.board_rect
        if not b.collidepoint(pos):
            return
        c = int((pos[0] - b.x) // self.cell)
        r = int((pos[1] - b.y) // self.cell)
        arrow = self.board.arrow_at(r, c)
        if arrow is None:
            return
        view = self.view_of(arrow)
        res = self.board.click(arrow)
        if res["ok"]:
            # 起飞：立刻从逻辑棋盘移除（不妨碍后续判定），视觉上继续飞
            self.board.remove(arrow)
            dr, dc = DELTA[arrow.d]
            view.state = "fly"
            view.vx = dc * 420.0          # 列 -> 屏幕 x
            view.vy = dr * 420.0          # 行 -> 屏幕 y
            self.rings.append(Ring(view.cx, view.cy))
            self.floats.append(FloatText("飞出！", view.cx, view.cy - self.cell * 0.5,
                                         C_ARROW, size=26, life=0.7))
            sound.play("pick_ok")        # 正确选择 -> 掌声
        else:
            blocker = res["blocker"]
            view.shake_t = 0.45
            view.flash_t = 0.45
            bv = self.view_of(blocker)
            if bv:
                bv.flash_t = 0.45
            self.floats.append(FloatText(
                "撞上了！被朝%s的箭头挡住" % DIR_NAME_CN[blocker.d],
                view.cx, view.cy - self.cell * 0.5, C_RED, size=26, life=1.1))
            sound.play("pick_bad")       # 错误选择 -> 失败音效
            if res["fail"]:
                self.fail_wait = 0.55

    def do_hint(self):
        a = find_hint(self.board)
        if a is None:
            return
        v = self.view_of(a)
        if v:
            v.hint_t = 1.2
            self.floats.append(FloatText("这个能飞", v.cx, v.cy - self.cell * 0.6,
                                         C_GREEN, size=24, life=1.0))

    # ------------------------------------------------ 更新
    def update(self, dt):
        mouse = pygame.mouse.get_pos()
        for btn in self._visible_buttons():
            btn.update_hover(mouse)

        if self.state == self.STATE_MENU:
            self.demo.update(dt)      # 菜单里的小棋盘自动演示
            return

        for v in self.views:
            v.update(dt, self.board_rect)
        self.floats = [f for f in self.floats if f.update(dt)]
        self.rings = [rg for rg in self.rings if rg.update(dt)]
        # 飞完的视图清掉
        if any(v.state == "dead" for v in self.views):
            self.views = [v for v in self.views if v.state != "dead"]

        if self.state == self.STATE_PLAY:
            self.elapsed += dt                       # 只在游戏进行中计时
            if self.board.is_cleared() and not any(v.state == "fly" for v in self.views):
                self.clear_wait += dt
                if self.clear_wait > 0.35:
                    # 本关结束：累计失误、结算得分与星级
                    self.total_mistakes += self.board.max_mistakes - self.board.mistakes_left
                    self.commit_result()
                    self.clear_anim = 0.0
                    sound.play("fireworks")          # 通关 -> 烟花音效
                    if self.level_index + 1 < len(self.levels):
                        self.state = self.STATE_CLEAR
                    else:
                        sound.play("level_clear")    # 全部通关再补一段上行琶音
                        self.state = self.STATE_ALLCLEAR
            if self.fail_wait > 0:
                self.fail_wait -= dt
                if self.fail_wait <= 0:
                    self.state = self.STATE_FAIL
        elif self.state == self.STATE_CLEAR:
            self.clear_anim += dt                    # 通关弹窗里的星星出现动画

    def _visible_buttons(self):
        if self.state == self.STATE_MENU:
            return [self.btn_start, self.btn_more]
        if self.state == self.STATE_LEVELS:
            return [self.btn_back_lv, self.btn_random]
        if self.state == self.STATE_PLAY:
            return [self.btn_restart, self.btn_hint, self.btn_menu]
        if self.state == self.STATE_CLEAR:
            return [self.btn_next, self.btn_back2]
        if self.state == self.STATE_FAIL:
            return [self.btn_retry, self.btn_back2]
        return [self.btn_again]

    # ------------------------------------------------ 绘制
    def draw_backdrop(self):
        """AIGC 生成的底纹（已裁掉水印、柔化细网格），低透明度铺满窗口。"""
        bg = sprites.backdrop((WIN_W, WIN_H))
        if bg is not None:
            bg.set_alpha(95)
            self.screen.blit(bg, (0, 0))

    def draw(self):
        if self.state == self.STATE_MENU:
            self.draw_menu()                 # 菜单自带底纹（静态层已预渲染）
        elif self.state == self.STATE_LEVELS:
            self.draw_level_select()
        else:
            self.screen.fill(C_BG)
            self.draw_backdrop()
            if self.state == self.STATE_PLAY:
                self.draw_play()
            elif self.state == self.STATE_CLEAR:
                self.draw_play()
                self.draw_clear_overlay()
            elif self.state == self.STATE_FAIL:
                self.draw_play()
                self.draw_fail_overlay()
            elif self.state == self.STATE_ALLCLEAR:
                self.draw_allclear()
        pygame.display.flip()

    def _card(self, rect, fill=C_PANEL):
        """和游戏内棋盘同款的圆角卡片（浅阴影 + 细边框）。"""
        shadow = pygame.Rect(rect.x + 5, rect.y + 7, rect.w, rect.h)
        pygame.draw.rect(self.screen, (222, 228, 238), shadow, border_radius=16)
        pygame.draw.rect(self.screen, fill, rect, border_radius=16)
        pygame.draw.rect(self.screen, C_GRID, rect, 2, border_radius=16)

    def draw_menu(self):
        # 静态部分（底纹/标题/卡片/文字）预渲染缓存，每帧只 blit 一次 —— 菜单元素多，
        # 逐帧重新渲染大段中文最费时间，缓存后菜单帧耗时能降一半以上。
        if self._menu_layer is None:
            self._menu_layer = self._render_menu_static()
        self.screen.blit(self._menu_layer, (0, 0))

        # 动态部分：演示棋盘（会被裁在卡片内）与按钮（有悬停态）
        prev_clip = self.screen.get_clip()
        self.screen.set_clip(MENU_DEMO_CARD)
        self.demo.draw(self.screen)
        self.screen.set_clip(prev_clip)
        self.btn_start.draw(self.screen)
        self.btn_more.draw(self.screen)

    def _render_menu_static(self):
        """把菜单里不动的元素画到一张离屏 Surface 上（复用同一套绘制代码）。"""
        real_screen = self.screen
        layer = pygame.Surface((WIN_W, WIN_H))
        self.screen = layer
        try:
            self.screen.fill(C_BG)
            bg = sprites.backdrop((WIN_W, WIN_H))
            if bg is not None:
                bg.set_alpha(95)
                self.screen.blit(bg, (0, 0))

            # 标题：两侧各放一支箭头图片（朝内），和游戏里的箭头素材同一套
            title = self.font_title.render("一 箭 又 一 箭", True, C_TEXT)
            tx, ty = WIN_W / 2 - title.get_width() / 2, 38
            self.screen.blit(title, (tx, ty))
            cy = ty + title.get_height() / 2
            draw_arrow(self.screen, tx - 76, cy, 72, "R")
            draw_arrow(self.screen, tx + title.get_width() + 76, cy, 72, "L")

            sub = self.font_small.render(
                "点击箭头 → 前方到边界没有箭头阻挡时，它就会飞出棋盘", True, C_TEXT_SUB)
            self.screen.blit(sub, (WIN_W / 2 - sub.get_width() / 2,
                                   ty + title.get_height() + 4))

            # 左卡片：规则
            self._card(MENU_RULES_RECT)
            self.screen.blit(self.font_mid.render("玩法", True, C_TEXT), (84, 176))
            rules = [
                "· 箭头方向：上 / 下 / 左 / 右（鼠标悬停可预览前进光路）",
                "· 前方到边界之间没有其他箭头 → 点击后它就飞出并消失",
                "· 被别的箭头挡住 → 点不动，晃动变红，扣 1 次失误",
                "· 清空本关全部箭头进入下一关；失误用完则本关失败",
                "· 按用时与失误评 1~3 星（零失误且不超目标用时 = 三星）",
                "· 开始游戏打固定 5 关；“更多关卡”里可自选关卡或随机挑战",
            ]
            for i, line in enumerate(rules):
                img = self.font_small.render(line, True, C_TEXT)
                self.screen.blit(img, (84, 232 + i * 30))

            # 右卡片：自动演示小棋盘的卡片与说明（棋盘本身是动态的）
            self._card(MENU_DEMO_CARD, fill=(250, 252, 255))
            self.screen.blit(self.font_small.render("自动演示", True, C_TEXT_SUB), (702, 174))
            for i, line in enumerate(["每次只点能飞的箭头", "清空后自动换一局"]):
                cap = self.font_tiny.render(line, True, C_TEXT_SUB)
                self.screen.blit(cap, (MENU_DEMO_CARD.centerx - cap.get_width() / 2,
                                       392 + i * 24))

            foot = self.font_small.render(
                "快捷键：R 重新开始 · Esc 返回菜单 · M 静音　|　命令行：--random 随机布局 · --seed N 复现",
                True, C_TEXT_SUB)
            self.screen.blit(foot, (WIN_W / 2 - foot.get_width() / 2, 616))
        finally:
            self.screen = real_screen
        return layer

    def draw_level_select(self):
        """关卡选项：5 张同尺寸卡片（显示最佳星级与最高分）+ 返回 / 随机挑战。"""
        if self._lv_layer is None:
            self._lv_layer = self._render_level_select_static()
        self.screen.blit(self._lv_layer, (0, 0))
        # 动态部分：卡片悬停高亮 + 按钮
        mouse = pygame.mouse.get_pos()
        for i in range(len(CLASSIC_LEVELS)):
            if level_card_rect(i).collidepoint(mouse):
                pygame.draw.rect(self.screen, C_BTN_HOVER, level_card_rect(i),
                                 3, border_radius=16)
        self.btn_back_lv.draw(self.screen)
        self.btn_random.draw(self.screen)

    def _render_level_select_static(self):
        """把关卡选项里不动的部分也预渲染成一张图（成绩变化时才重建）。"""
        real_screen = self.screen
        layer = pygame.Surface((WIN_W, WIN_H))
        self.screen = layer
        try:
            self.screen.fill(C_BG)
            bg = sprites.backdrop((WIN_W, WIN_H))
            if bg is not None:
                bg.set_alpha(95)
                self.screen.blit(bg, (0, 0))

            title = self.font_title.render("更 多 关 卡", True, C_TEXT)
            self.screen.blit(title, (WIN_W / 2 - title.get_width() / 2, 34))
            sub = self.font_small.render(
                "点任意一关直接挑战 ｜ 成绩按「用时 + 失误」评星，最高分会存档",
                True, C_TEXT_SUB)
            self.screen.blit(sub, (WIN_W / 2 - sub.get_width() / 2, 116))

            for i, lv in enumerate(CLASSIC_LEVELS):
                rect = level_card_rect(i)
                self._card(rect)
                # level.name 形如「第1关 · 初次上手」
                parts = lv.name.split("·")
                num = parts[0].strip()
                theme = parts[1].strip() if len(parts) > 1 else ""
                img = self.font_hud.render(num, True, C_TEXT)
                self.screen.blit(img, (rect.centerx - img.get_width() / 2, rect.y + 20))
                img = self.font_tiny.render(theme, True, C_TEXT_SUB)
                self.screen.blit(img, (rect.centerx - img.get_width() / 2, rect.y + 54))

                info = [
                    "%d×%d 棋盘" % (lv.rows, lv.cols),
                    "%d 支箭头" % len(lv.arrow_specs()),
                    "失误上限 %d" % lv.mistakes,
                    "目标 %d 秒" % par_time(len(lv.arrow_specs())),
                ]
                for k, line in enumerate(info):
                    img = self.font_tiny.render(line, True, C_TEXT_SUB)
                    self.screen.blit(img, (rect.centerx - img.get_width() / 2,
                                           rect.y + 84 + k * 25))

                best = self.best_of_level(i)
                draw_star_row(self.screen, rect.centerx, rect.y + 194, 32,
                              best["stars"] if best else 0)
                txt = "最高 %d 分" % best["score"] if best else "尚未通关"
                img = self.font_tiny.render(txt, True, C_GREEN if best else C_TEXT_SUB)
                self.screen.blit(img, (rect.centerx - img.get_width() / 2, rect.y + 218))

            foot = self.font_small.render(
                "三星：零失误且不超目标用时　｜　两星：失误 ≤1 且用时不超过 1.6 倍目标",
                True, C_TEXT_SUB)
            self.screen.blit(foot, (WIN_W / 2 - foot.get_width() / 2, 430))
            foot2 = self.font_small.render(
                "快捷键：Esc 返回菜单 · M 静音　｜　通关后点“下一关”继续，点“返回菜单”回这里挑关",
                True, C_TEXT_SUB)
            self.screen.blit(foot2, (WIN_W / 2 - foot2.get_width() / 2, 690))
        finally:
            self.screen = real_screen
        return layer

    def draw_play(self):
        level = self.levels[self.level_index]
        # 顶部 HUD
        pygame.draw.rect(self.screen, C_HUD, (0, 0, WIN_W, 112))
        pygame.draw.line(self.screen, C_GRID, (0, 112), (WIN_W, 112), 2)

        t1 = self.font_hud.render(level.name, True, C_TEXT)
        self.screen.blit(t1, (40, 30))

        t2 = self.font_hud.render(
            "剩余箭头 %d/%d" % (self.board.remaining(), self.board.total()), True, C_TEXT)
        self.screen.blit(t2, (300, 30))

        # 本局累计得分（结算时按用时与失误加星）
        t_score = self.font_hud.render("得分 %d" % self.run_score, True, C_TEXT)
        self.screen.blit(t_score, (480, 30))

        t3 = self.font_small.render("剩余失误", True, C_TEXT_SUB)
        self.screen.blit(t3, (626, 14))
        for i in range(self.board.max_mistakes):
            draw_heart(self.screen, 626 + i * 44, 68, 36,
                       filled=(i < self.board.mistakes_left))

        # 本局模式：随机布局显示种子，便于复现同一批关卡
        if self.mode == "classic":
            mode_txt = "经典布局 · 固定 %d 关" % len(self.levels)
        else:
            mode_txt = "随机布局 · 种子 %d" % self.run_seed
        if sound.muted:
            mode_txt += " · 静音"
        t4 = self.font_small.render(mode_txt, True, C_TEXT_SUB)
        self.screen.blit(t4, (40, 70))

        # 用时 / 目标用时（超时目标时间后变红提醒）
        par = self.par_of_level(self.level_index)
        time_txt = "用时 %.1fs / 目标 %.0fs" % (self.elapsed, par)
        color = C_TEXT_SUB if self.elapsed <= par else C_RED
        t5 = self.font_tiny.render(time_txt, True, color)
        self.screen.blit(t5, (600 - t5.get_width(), 74))

        # 棋盘
        b = self.board_rect
        shadow = pygame.Rect(b.x + 6, b.y + 8, b.w, b.h)
        pygame.draw.rect(self.screen, (226, 231, 239), shadow, border_radius=14)
        pygame.draw.rect(self.screen, C_BOARD_BG, b, border_radius=12)
        pygame.draw.rect(self.screen, C_BOARD_EDGE, b, 3, border_radius=12)
        for i in range(1, self.board.cols):
            x = b.x + i * self.cell
            pygame.draw.line(self.screen, C_GRID, (x, b.y + 2), (x, b.bottom - 2), 1)
        for j in range(1, self.board.rows):
            y = b.y + j * self.cell
            pygame.draw.line(self.screen, C_GRID, (b.x + 2, y), (b.right - 2, y), 1)

        # 鼠标悬停：显示该箭头的路径预判（绿=通，红=挡）
        if self.state == self.STATE_PLAY:
            mouse = pygame.mouse.get_pos()
            if b.collidepoint(mouse):
                c = int((mouse[0] - b.x) // self.cell)
                r = int((mouse[1] - b.y) // self.cell)
                arrow = self.board.arrow_at(r, c)
                if arrow:
                    self.draw_path_preview(arrow)

        # 箭头们
        for v in self.views:
            v.draw(self.screen, self.cell)

        for rg in self.rings:
            rg.draw(self.screen, self.cell)
        for f in self.floats:
            f.draw(self.screen)

        # 底部按钮
        self.btn_restart.draw(self.screen)
        self.btn_hint.draw(self.screen)
        self.btn_menu.draw(self.screen)
        tip = self.font_small.render("快捷键：R 重新开始 · Esc 返回菜单", True, C_TEXT_SUB)
        self.screen.blit(tip, (645, WIN_H - 62))

    def draw_path_preview(self, arrow):
        """悬停时画出箭头前进方向的光路，直观展示路径检测。"""
        b = self.board_rect
        clear, blocker = self.board.scan(arrow)
        color = C_GREEN if clear else C_RED
        dx, dy = DELTA[arrow.d]
        r, c = arrow.r, arrow.c
        # 逐格涂半透明色，直到边界或挡路者
        while True:
            r += dx
            c += dy
            if not (0 <= r < self.board.rows and 0 <= c < self.board.cols):
                break
            cell_rect = pygame.Rect(b.x + c * self.cell, b.y + r * self.cell,
                                    self.cell, self.cell)
            s = pygame.Surface((self.cell, self.cell), pygame.SRCALPHA)
            s.fill((*color, 46))
            self.screen.blit(s, cell_rect.topleft)
            if blocker is not None and (r, c) == (blocker.r, blocker.c):
                pygame.draw.rect(self.screen, color,
                                 cell_rect.inflate(-6, -6), 4, border_radius=8)
                break

        # 目标箭头本身加框
        own = pygame.Rect(b.x + arrow.c * self.cell, b.y + arrow.r * self.cell,
                          self.cell, self.cell).inflate(-6, -6)
        pygame.draw.rect(self.screen, color, own, 3, border_radius=8)

    def _overlay(self):
        s = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        s.fill((20, 28, 40, 150))
        self.screen.blit(s, (0, 0))

    def draw_clear_overlay(self):
        self._overlay()
        self._panel(WIN_W / 2 - 260, 185, 520, 300)
        img = self.font_big.render("第 %d 关 完成！" % (self.level_index + 1), True, C_GREEN)
        self.screen.blit(img, (WIN_W / 2 - img.get_width() / 2, 205))

        # 星级（逐颗弹出的小动画）
        res = self.result or evaluate(self.elapsed, 0, 1)
        draw_star_row(self.screen, WIN_W / 2, 292, 56, res["stars"],
                      progress=self.clear_anim)

        total = len(self.levels[self.level_index].arrow_specs())
        clean = "零失误" if res["mistakes_used"] == 0 else "失误 %d 次" % res["mistakes_used"]
        info = self.font_small.render(
            "用时 %.1fs / 目标 %.0fs · %s · 本关 %d 分" %
            (res["elapsed"], res["par"], clean, res["score"]), True, C_TEXT_SUB)
        self.screen.blit(info, (WIN_W / 2 - info.get_width() / 2, 336))

        sub = self.font_tiny.render(
            "%d 支箭头 · 本局累计 %d 分%s" %
            (total, self.run_score,
             "　·　已刷新本关最高分" if res.get("new_record") else ""), True, C_TEXT_SUB)
        self.screen.blit(sub, (WIN_W / 2 - sub.get_width() / 2, 364))

        self.btn_next.draw(self.screen)
        self.btn_back2.draw(self.screen)

    def draw_fail_overlay(self):
        self._overlay()
        self._panel(WIN_W / 2 - 260, 185, 520, 300)
        img = self.font_big.render("本关失败", True, C_RED)
        self.screen.blit(img, (WIN_W / 2 - img.get_width() / 2, 215))
        info = self.font_small.render("失误次数已用完，还剩 %d 支箭头" % self.board.remaining(),
                                      True, C_TEXT_SUB)
        self.screen.blit(info, (WIN_W / 2 - info.get_width() / 2, 300))
        tip = self.font_tiny.render("失败不计分；点“重新挑战”再打一次，或回关卡选项换一关",
                                    True, C_TEXT_SUB)
        self.screen.blit(tip, (WIN_W / 2 - tip.get_width() / 2, 334))
        self.btn_retry.draw(self.screen)
        self.btn_back2.draw(self.screen)

    def draw_allclear(self):
        self._overlay()
        self._panel(WIN_W / 2 - 300, 130, 600, 460)
        img = self.font_big.render("全 部 通 关 ！", True, C_GREEN)
        self.screen.blit(img, (WIN_W / 2 - img.get_width() / 2, 172))
        info = self.font_mid.render("全部 %d 关清空 · 本局总分 %d" %
                                    (len(self.levels), self.run_score), True, C_TEXT)
        self.screen.blit(info, (WIN_W / 2 - info.get_width() / 2, 246))
        if self.mode == "classic":
            stars = [self.best_of_level(i) for i in range(len(self.levels))]
            got = sum(s["stars"] for s in stars if s)
            sub = self.font_small.render(
                "累计失误 %d 次　·　经典关卡累计星数 %d / %d"
                % (self.total_mistakes, got, MAX_STARS * len(self.levels)), True, C_TEXT_SUB)
        else:
            sub = self.font_small.render("累计失误 %d 次 · 本局种子 %d"
                                         % (self.total_mistakes, self.run_seed), True, C_TEXT_SUB)
        self.screen.blit(sub, (WIN_W / 2 - sub.get_width() / 2, 292))
        thanks = self.font_small.render("点击“再来一遍”会重新生成一批关卡", True, C_TEXT_SUB)
        self.screen.blit(thanks, (WIN_W / 2 - thanks.get_width() / 2, 326))
        # 一排小箭头庆祝
        for i, d in enumerate(["U", "R", "D", "L", "U", "R", "D", "L"]):
            draw_arrow(self.screen, WIN_W / 2 - 245 + i * 70, 400, 44, d, C_ARROW)
        self.btn_again.draw(self.screen)

    def _panel(self, x, y, w, h):
        r = pygame.Rect(x, y, w, h)
        pygame.draw.rect(self.screen, C_PANEL, r, border_radius=18)
        pygame.draw.rect(self.screen, C_GRID, r, 2, border_radius=18)

    # ------------------------------------------------ 主循环
    def run(self):
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self.on_click(event.pos)
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        if self.state == self.STATE_PLAY:
                            self.state = self.STATE_MENU
                        elif self.state == self.STATE_LEVELS:
                            self.state = self.STATE_MENU
                    elif event.key == pygame.K_m:
                        sound.toggle_mute()          # 静音开关
                    elif event.key == pygame.K_r and self.state == self.STATE_PLAY:
                        self.restart_level()
            self.update(dt)
            self.draw()
        pygame.quit()
        sys.exit(0)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="一箭又一箭（Pygame 版）")
    parser.add_argument("--random", action="store_true",
                        help="随机布局：每次开局现场生成 5 关（默认是固定 5 关）")
    parser.add_argument("--classic", action="store_true",
                        help="固定 5 关经典关卡（默认行为，保留此参数便于兼容）")
    parser.add_argument("--level", type=int, default=None,
                        help="直接从第 N 关开始（1 起）")
    parser.add_argument("--seed", type=int, default=None,
                        help="随机模式的种子：同一个种子生成完全相同的关卡")
    args = parser.parse_args()

    game = Game(mode="random" if args.random else "classic", seed=args.seed)
    if args.level:
        game.start_level(max(0, min(len(game.levels) - 1, args.level - 1)))
    game.run()
