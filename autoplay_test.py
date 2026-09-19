# -*- coding: utf-8 -*-
"""
自动试玩测试（不弹窗口，SDL 使用 dummy 驱动）

做三件事：
1. 每一关都用求解器给出的通关顺序，通过 Game.on_click() 走真实点击路径，
   验证：全部箭头飞出、关卡判定为通关、失误为 0；
2. 专门测试“被挡箭头”：点它 -> 失误数 -1、箭头仍在、出现碰撞动画；
3. 测试失败流程：把失误点光 -> 进入失败界面；测试重新开始按钮 -> 棋盘复原。

同时沿途截图（screenshots/），既是回归测试，也是“每一关都被实际玩过”的记录。

用法：
    python tools/autoplay_test.py
"""
import os
import sys

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

import pygame  # noqa: E402

from game_core import solve_level, DELTA  # noqa: E402
from levels import LEVELS  # noqa: E402
from main import Game, C_RED  # noqa: E402

SHOT_DIR = os.path.join(BASE, "screenshots")
os.makedirs(SHOT_DIR, exist_ok=True)
FAILED = []


def check(cond, msg):
    tag = "PASS" if cond else "FAIL"
    print("  [%s] %s" % (tag, msg))
    if not cond:
        FAILED.append(msg)


def snap(game, name):
    game.draw()
    pygame.image.save(game.screen, os.path.join(SHOT_DIR, name + ".png"))
    print("  截图 -> screenshots/%s.png" % name)


def run_frames(game, seconds, shot_name=None, shot_at=None):
    """推进若干秒的游戏时间；可选在途中截一张图。"""
    frames = int(seconds * 60)
    for i in range(frames):
        game.update(1 / 60)
        if shot_name and shot_at is not None and i == shot_at:
            snap(game, shot_name)
    game.draw()


def click_cell(game, r, c):
    x, y = game.cell_center(r, c)
    game.on_click((x, y))


def play_level(game, idx):
    print("\n== 第 %d 关：%s ==" % (idx + 1, LEVELS[idx].name))
    order = solve_level(LEVELS[idx])
    total = len(LEVELS[idx].arrow_specs())
    check(order is not None and len(order) == total,
          "求解器给出 %d 步通关顺序" % (0 if order is None else len(order)))
    for k, a in enumerate(order):
        click_cell(game, a[0], a[1])
        # 第一支箭头：校验飞行动画方向与箭头朝向一致（防止行列/xy 混淆类 bug）
        if k == 0:
            flying = [v for v in game.views if v.state == "fly" and v.arrow.key() == a]
            if flying:
                dr, dc = DELTA[a[2]]
                v = flying[0]
                check((dc == 0 or (v.vx > 0) == (dc > 0)) and
                      (dr == 0 or (v.vy > 0) == (dr > 0)),
                      "飞行动画方向与朝向一致（%s）" % a[2])
                for _ in range(9):
                    game.update(1 / 60)
                snap(game, "03_flying")
        # 等这一支飞出画面
        while any(v.state == "fly" for v in game.views):
            game.update(1 / 60)
    run_frames(game, 0.6)
    check(game.board.is_cleared(), "全部箭头已飞出（剩余 %d）" % game.board.remaining())
    check(game.board.mistakes_left == game.board.max_mistakes, "零失误通关")
    expected = Game.STATE_ALLCLEAR if idx + 1 == len(LEVELS) else Game.STATE_CLEAR
    check(game.state == expected, "关卡完成判定 state=%s" % game.state)
    snap(game, "level%d_clear" % (idx + 1))


def main():
    game = Game(headless=True)

    # ---- 菜单
    print("== 菜单界面 ==")
    run_frames(game, 0.1)
    snap(game, "00_menu")
    game.on_click((game.btn_start.rect.centerx, game.btn_start.rect.centery))
    check(game.state == Game.STATE_PLAY, "点击开始进入第 1 关")

    # ---- 第 1 关：先故意点一支被挡的箭头，验证碰撞逻辑
    print("\n== 碰撞与失误测试（第 1 关）==")
    blocked = game.board.blocked_arrows()
    check(len(blocked) > 0, "第 1 关开局存在被挡箭头 %d 支" % len(blocked))
    before = game.board.mistakes_left
    a = blocked[0]
    click_cell(game, a.r, a.c)
    run_frames(game, 0.15, "01_crash", shot_at=3)   # 晃动进行中截图
    check(game.board.mistakes_left == before - 1, "失误数 %d -> %d" % (before, game.board.mistakes_left))
    check(game.board.arrow_at(a.r, a.c) is a, "被挡箭头没有消失")
    view = game.view_of(a)
    check(view is not None and view.shake_t > 0, "碰撞箭头处于晃动动画中")
    # 剩余箭头数不变
    check(game.board.remaining() == game.board.total(), "箭头总数没有减少")

    # ---- 重新开始按钮
    print("\n== 重新开始测试 ==")
    game.on_click((game.btn_restart.rect.centerx, game.btn_restart.rect.centery))
    check(game.state == Game.STATE_PLAY and game.board.mistakes_left == game.board.max_mistakes,
          "点击重新开始后失误数复原")
    check(game.board.remaining() == game.board.total(), "棋盘恢复到初始状态")
    snap(game, "02_after_restart")

    # ---- 逐关通关
    for i in range(len(LEVELS)):
        if i > 0:
            game.on_click((game.btn_next.rect.centerx, game.btn_next.rect.centery))
            check(game.level_index == i and game.state == Game.STATE_PLAY,
                  "进入第 %d 关" % (i + 1))
            snap(game, "level%d_start" % (i + 1))
        else:
            snap(game, "level1_start")
        play_level(game, i)

    # ---- 全部通关界面
    run_frames(game, 0.3)
    snap(game, "09_allclear")

    # ---- 失败流程：回到第 1 关，把失误点光
    print("\n== 失败流程测试 ==")
    game.start_level(0)
    while game.state == Game.STATE_PLAY:
        blocked = game.board.blocked_arrows()
        if not blocked:
            # 理论上不会发生：失误还没点光就已无被挡箭头则直接通关
            break
        a = blocked[0]
        click_cell(game, a.r, a.c)
        run_frames(game, 0.7)          # 失败有 0.55s 的红闪延迟
    check(game.state == Game.STATE_FAIL, "失误耗尽后进入失败界面 state=%s" % game.state)
    check(game.board.remaining() > 0, "失败时棋盘上仍有箭头")
    snap(game, "08_fail")
    game.on_click((game.btn_retry.rect.centerx, game.btn_retry.rect.centery))
    check(game.state == Game.STATE_PLAY and game.board.mistakes_left == game.board.max_mistakes,
          "失败后可重新开始本关")

    print("\n" + "=" * 50)
    if FAILED:
        print("有 %d 项失败：%s" % (len(FAILED), FAILED))
        sys.exit(1)
    print("全部测试通过 ✔  每一关均按求解顺序实际通关。")
    pygame.quit()


if __name__ == "__main__":
    main()
