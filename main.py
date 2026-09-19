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
import math
import os
import sys

import pygame

from game_core import Board, DELTA, DIR_NAME_CN, find_hint
from levels import LEVELS

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
C_ARROW_DARK = (30, 78, 162)
C_RED = (225, 70, 75)             # 碰撞 / 失误：红
C_GREEN = (46, 160, 95)           # 可飞出提示：绿
C_BTN = (44, 107, 209)
C_BTN_HOVER = (62, 128, 232)
C_BTN_TEXT = (255, 255, 255)
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


# ------------------------------------------------------------------ 画箭头
def draw_arrow(surface, cx, cy, size, direction, color):
    """在 (cx, cy) 为中心、边长 size 的范围内画一个指向 direction 的箭头。"""
    # DELTA 是 (行增量, 列增量)，转成屏幕 (x, y)：列 -> x，行 -> y（行向下增长）
    dr, dc = DELTA[direction]
    ux, uy = dc, dr                  # 单位向量
    px_, py_ = -uy, ux               # 垂直向量
    s = size * 0.74

    tip = (cx + ux * s * 0.52, cy + uy * s * 0.52)      # 箭尖
    hb = (cx + ux * s * 0.08, cy + uy * s * 0.08)       # 箭头底部中心
    tail = (cx - ux * s * 0.46, cy - uy * s * 0.46)     # 箭尾
    shaft_w = max(4, int(s * 0.28))
    head_w = s * 0.64
    h1 = (hb[0] + px_ * head_w / 2, hb[1] + py_ * head_w / 2)
    h2 = (hb[0] - px_ * head_w / 2, hb[1] - py_ * head_w / 2)

    dark = tuple(max(0, int(c * 0.78)) for c in color)
    # 箭杆（圆头线条）+ 三角形箭头
    pygame.draw.circle(surface, color, (int(tail[0]), int(tail[1])), shaft_w // 2)
    pygame.draw.line(surface, color, tail, hb, shaft_w)
    pygame.draw.polygon(surface, color, [tip, h1, h2])
    pygame.draw.polygon(surface, dark, [tip, h1, h2], 2)


def draw_heart(surface, cx, cy, size, color):
    """程序画一个爱心，表示剩余失误次数。"""
    r = size * 0.25
    top = cy - size * 0.05
    left_c = (cx - r, top)
    right_c = (cx + r, top)
    bottom = (cx, cy + size * 0.42)
    pygame.draw.circle(surface, color, (int(left_c[0]), int(left_c[1])), int(r))
    pygame.draw.circle(surface, color, (int(right_c[0]), int(right_c[1])), int(r))
    pygame.draw.polygon(surface, color, [
        (left_c[0] - r * 0.92, top + r * 0.35),
        (right_c[0] + r * 0.92, top + r * 0.35),
        bottom,
    ])


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

        color = C_ARROW
        if self.flash_t > 0:
            color = lerp_color(C_ARROW, C_RED, min(1.0, self.flash_t / 0.45 * 1.4))
        draw_arrow(surface, self.cx + ox, self.cy + oy, cell, self.arrow.d, color)

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
        img.set_alpha(a)
        surface.blit(img, (self.x - img.get_width() / 2, self.y - 40 * t - img.get_height() / 2))


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


class Button:
    def __init__(self, rect, text, font=None, normal=C_BTN, hover=C_BTN_HOVER):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.normal = normal
        self.hover = hover
        self.font = font or get_font(24, bold=True)
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
    STATE_PLAY = "play"
    STATE_CLEAR = "clear"            # 本关通关（过渡）
    STATE_FAIL = "fail"
    STATE_ALLCLEAR = "allclear"

    def __init__(self, headless=False):
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy" if headless else "windib")
        pygame.init()
        pygame.display.set_caption("一箭又一箭")
        self.screen = pygame.display.set_mode((WIN_W, WIN_H))
        self.clock = pygame.time.Clock()
        self.running = True
        self.headless = headless

        self.font_title = get_font(64, bold=True)
        self.font_big = get_font(44, bold=True)
        self.font_mid = get_font(28, bold=True)
        self.font_small = get_font(20)
        self.font_hud = get_font(24, bold=True)

        self.level_index = 0
        self.total_mistakes = 0      # 全程失误统计（全部通关界面展示）
        self.state = self.STATE_MENU
        self.views = []              # ArrowView 列表
        self.floats = []             # 漂浮文字
        self.rings = []
        self.clear_wait = 0.0        # 清空后等最后一支箭飞完
        self.fail_wait = 0.0

        # 各界面按钮
        self.btn_start = Button((WIN_W / 2 - 110, 430, 220, 62), "开 始 游 戏")
        self.btn_restart = Button((70, WIN_H - 78, 170, 54), "重新开始")
        self.btn_hint = Button((260, WIN_H - 78, 170, 54), "提示一下")
        self.btn_menu = Button((450, WIN_H - 78, 170, 54), "返回菜单")
        self.btn_next = Button((WIN_W / 2 - 220, 405, 200, 58), "下一关 →")
        self.btn_retry = Button((WIN_W / 2 - 220, 405, 200, 58), "重新挑战")
        self.btn_back2 = Button((WIN_W / 2 + 20, 405, 200, 58), "返回菜单")
        self.btn_again = Button((WIN_W / 2 - 110, 500, 220, 60), "再来一遍")

        self.start_level(0)
        self.state = self.STATE_MENU      # 开机先进菜单

    # ------------------------------------------------ 关卡 / 棋盘
    def start_level(self, idx):
        self.level_index = idx
        self.board = Board(LEVELS[idx])
        self._layout()
        self.state = self.STATE_PLAY
        self.floats.clear()
        self.rings.clear()
        self.clear_wait = 0.0
        self.fail_wait = 0.0
        self._sync_views()

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
                self.total_mistakes = 0
                self.start_level(0)
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
                self.state = self.STATE_MENU
            return

        if self.state == self.STATE_FAIL:
            if self.btn_retry.hit(pos):
                self.start_level(self.level_index)
            elif self.btn_back2.hit(pos):
                self.state = self.STATE_MENU
            return

        if self.state == self.STATE_ALLCLEAR:
            if self.btn_again.hit(pos):
                self.total_mistakes = 0
                self.start_level(0)
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
        else:
            blocker = res["blocker"]
            view.shake_t = 0.45
            view.flash_t = 0.45
            bv = self.view_of(blocker)
            if bv:
                bv.flash_t = 0.45
            self.floats.append(FloatText(
                "撞上了！前方有箭头挡路",
                view.cx, view.cy - self.cell * 0.5, C_RED, size=26, life=1.1))
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
        for v in self.views:
            v.update(dt, self.board_rect)
        self.floats = [f for f in self.floats if f.update(dt)]
        self.rings = [rg for rg in self.rings if rg.update(dt)]
        # 飞完的视图清掉
        if any(v.state == "dead" for v in self.views):
            self.views = [v for v in self.views if v.state != "dead"]

        if self.state == self.STATE_PLAY:
            if self.board.is_cleared() and not any(v.state == "fly" for v in self.views):
                self.clear_wait += dt
                if self.clear_wait > 0.35:
                    # 本关结束，累计本关失误次数
                    self.total_mistakes += self.board.max_mistakes - self.board.mistakes_left
                    if self.level_index + 1 < len(LEVELS):
                        self.state = self.STATE_CLEAR
                    else:
                        self.state = self.STATE_ALLCLEAR
            if self.fail_wait > 0:
                self.fail_wait -= dt
                if self.fail_wait <= 0:
                    self.state = self.STATE_FAIL

    def _visible_buttons(self):
        if self.state == self.STATE_MENU:
            return [self.btn_start]
        if self.state == self.STATE_PLAY:
            return [self.btn_restart, self.btn_hint, self.btn_menu]
        if self.state == self.STATE_CLEAR:
            return [self.btn_next, self.btn_back2]
        if self.state == self.STATE_FAIL:
            return [self.btn_retry, self.btn_back2]
        return [self.btn_again]

    # ------------------------------------------------ 绘制
    def draw(self):
        self.screen.fill(C_BG)
        if self.state == self.STATE_MENU:
            self.draw_menu()
        elif self.state == self.STATE_PLAY:
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

    def draw_menu(self):
        title = self.font_title.render("一 箭 又 一 箭", True, C_TEXT)
        self.screen.blit(title, (WIN_W / 2 - title.get_width() / 2, 130))

        sub = self.font_mid.render("点击箭头，让它飞出棋盘", True, C_TEXT_SUB)
        self.screen.blit(sub, (WIN_W / 2 - sub.get_width() / 2, 230))

        rules = [
            "· 箭头方向：上 / 下 / 左 / 右",
            "· 前进方向到边界之间没有其他箭头时，点击即可飞出",
            "· 路径上被其他箭头挡住时，点击算一次失误（箭头会晃动变红）",
            "· 清空本关全部箭头进入下一关，失误次数耗尽则本关失败",
            "· 共 %d 关，难度递增" % len(LEVELS),
        ]
        for i, line in enumerate(rules):
            img = self.font_small.render(line, True, C_TEXT)
            self.screen.blit(img, (WIN_W / 2 - 330, 292 + i * 31))

        # 小演示：四个方向的箭头
        demo_y = 452
        draw_arrow(self.screen, WIN_W / 2 - 150, demo_y, 46, "R", C_ARROW)
        draw_arrow(self.screen, WIN_W / 2 - 60, demo_y, 46, "U", C_ARROW)
        draw_arrow(self.screen, WIN_W / 2 + 30, demo_y, 46, "D", C_ARROW)
        draw_arrow(self.screen, WIN_W / 2 + 120, demo_y, 46, "L", C_ARROW)
        for i, (x, t) in enumerate([(-150, "右"), (-60, "上"), (30, "下"), (120, "左")]):
            img = self.font_small.render(t, True, C_TEXT_SUB)
            self.screen.blit(img, (WIN_W / 2 + x - img.get_width() / 2, demo_y + 34))

        self.btn_start.rect.y = 535
        self.btn_start.draw(self.screen)

    def draw_play(self):
        level = LEVELS[self.level_index]
        # 顶部 HUD
        pygame.draw.rect(self.screen, C_HUD, (0, 0, WIN_W, 112))
        pygame.draw.line(self.screen, C_GRID, (0, 112), (WIN_W, 112), 2)

        t1 = self.font_hud.render(level.name, True, C_TEXT)
        self.screen.blit(t1, (40, 30))

        t2 = self.font_hud.render(
            "剩余箭头：%d / %d" % (self.board.remaining(), self.board.total()), True, C_TEXT)
        self.screen.blit(t2, (330, 30))

        t3 = self.font_small.render("剩余失误", True, C_TEXT_SUB)
        self.screen.blit(t3, (610, 20))
        for i in range(self.board.max_mistakes):
            color = C_RED if i < self.board.mistakes_left else (205, 210, 218)
            draw_heart(self.screen, 640 + i * 42, 66, 30, color)

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
        self.screen.blit(img, (WIN_W / 2 - img.get_width() / 2, 225))
        info = self.font_small.render(
            "本关失误 %d 次 · 用了 %d 次点击" % (
                LEVELS[self.level_index].mistakes - self.board.mistakes_left,
                self.board.click_count),
            True, C_TEXT_SUB)
        self.screen.blit(info, (WIN_W / 2 - info.get_width() / 2, 300))
        self.btn_next.draw(self.screen)
        self.btn_back2.draw(self.screen)

    def draw_fail_overlay(self):
        self._overlay()
        self._panel(WIN_W / 2 - 260, 185, 520, 300)
        img = self.font_big.render("本关失败", True, C_RED)
        self.screen.blit(img, (WIN_W / 2 - img.get_width() / 2, 225))
        info = self.font_small.render("失误次数已用完，还剩 %d 支箭头，再试一次吧"
                                      % self.board.remaining(), True, C_TEXT_SUB)
        self.screen.blit(info, (WIN_W / 2 - info.get_width() / 2, 300))
        self.btn_retry.draw(self.screen)
        self.btn_back2.draw(self.screen)

    def draw_allclear(self):
        self._overlay()
        self._panel(WIN_W / 2 - 300, 130, 600, 460)
        img = self.font_big.render("全 部 通 关 ！", True, C_GREEN)
        self.screen.blit(img, (WIN_W / 2 - img.get_width() / 2, 180))
        info = self.font_mid.render("全部 %d 关清空，累计失误 %d 次" %
                                    (len(LEVELS), self.total_mistakes), True, C_TEXT)
        self.screen.blit(info, (WIN_W / 2 - info.get_width() / 2, 270))
        thanks = self.font_small.render("感谢游玩 —— 点击“再来一遍”重新挑战", True, C_TEXT_SUB)
        self.screen.blit(thanks, (WIN_W / 2 - thanks.get_width() / 2, 330))
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
                    elif event.key == pygame.K_r and self.state == self.STATE_PLAY:
                        self.restart_level()
            self.update(dt)
            self.draw()
        pygame.quit()
        sys.exit(0)


if __name__ == "__main__":
    Game().run()
