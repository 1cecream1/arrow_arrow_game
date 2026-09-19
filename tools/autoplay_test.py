# -*- coding: utf-8 -*-
"""
自动试玩测试（不弹窗口，SDL 用 dummy 驱动、音频也走 dummy）

覆盖内容：
1. 计分 / 星级：evaluate() 纯函数单测（零失误快=3星、失误 1 次=2星、又慢又错=1星、
   分数保底与单调性）；
2. 音效接线：点对 -> pick_ok、点错 -> pick_bad、通关 -> fireworks、静音后不再出声；
3. 关卡选项界面：菜单「更多关卡」-> 关卡选择 -> 点某关卡片直接进对应关卡 -> 返回菜单；
4. 本地成绩记录：通关写入 records.json、只有更高分才覆盖、失败不计分；
5. 经典 5 关完整流程 + 随机关卡自动通关（每关都按求解顺序真实点击）。

沿途截图（screenshots/），既是回归测试，也是“每个界面/每关都实际跑过”的记录。

用法：
    python tools/autoplay_test.py
"""
import os
import sys
import tempfile

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

import pygame  # noqa: E402

from game_core import (analyze_specs, build_run, evaluate, par_time,  # noqa: E402
                       solve_level, DELTA)
from levels import CLASSIC_LEVELS  # noqa: E402
from main import Game, level_card_rect, load_records  # noqa: E402
from sound import sound  # noqa: E402

SHOT_DIR = os.path.join(BASE, "screenshots")
os.makedirs(SHOT_DIR, exist_ok=True)
FAILED = []
RANDOM_RUNS = 6          # 随机关卡自动通关的局数


def check(cond, msg):
    print("  [%s] %s" % ("PASS" if cond else "FAIL", msg))
    if not cond:
        FAILED.append(msg)


def snap(game, name):
    game.draw()
    pygame.image.save(game.screen, os.path.join(SHOT_DIR, name + ".png"))
    print("  截图 -> screenshots/%s.png" % name)


def run_frames(game, seconds, shot_name=None, shot_at=None):
    frames = int(seconds * 60)
    for i in range(frames):
        game.update(1 / 60)
        if shot_name and shot_at is not None and i == shot_at:
            snap(game, shot_name)
    game.draw()


def click_cell(game, r, c):
    game.on_click(game.cell_center(r, c))


def click_btn(game, btn):
    game.on_click(btn.rect.center)


def finish_level(game, shot_prefix=None):
    """用求解顺序把当前关打完（走真实点击路径）。"""
    lv = game.levels[game.level_index]
    order = solve_level(lv)
    check(order is not None and len(order) == len(lv.arrow_specs()),
          "第%d关 求解器给出 %d 步通关顺序" % (game.level_index + 1,
                                             0 if order is None else len(order)))
    for k, a in enumerate(order):
        click_cell(game, a[0], a[1])
        if k == 0 and shot_prefix:
            flying = [v for v in game.views if v.state == "fly" and v.arrow.key() == a]
            if flying:
                dr, dc = DELTA[a[2]]
                v = flying[0]
                check((dc == 0 or (v.vx > 0) == (dc > 0)) and
                      (dr == 0 or (v.vy > 0) == (dr > 0)),
                      "飞行动画方向与朝向一致（%s）" % a[2])
                for _ in range(9):
                    game.update(1 / 60)
                snap(game, shot_prefix)
        while any(v.state == "fly" for v in game.views):
            game.update(1 / 60)
    run_frames(game, 1.4)           # 等结算弹窗和星星动画播完


# ---------------------------------------------------------------- 1. 计分
def test_scoring():
    print("\n== 计分与星级（纯函数）==")
    n = 9
    par = par_time(n)
    fast = evaluate(par * 0.6, 0, n)
    one_mistake = evaluate(par * 1.2, 1, n)
    slow_bad = evaluate(par * 2.0, 2, n)
    check(fast["stars"] == 3 and fast["score"] == 1000,
          "零失误且快：3 星 / %d 分" % fast["score"])
    check(one_mistake["stars"] == 2, "失误 1 次且略超时：%d 星" % one_mistake["stars"])
    check(slow_bad["stars"] == 1, "失误 2 次且严重超时：%d 星" % slow_bad["stars"])
    check(fast["score"] > one_mistake["score"] > slow_bad["score"],
          "分数随失误/超时递减：%d > %d > %d"
          % (fast["score"], one_mistake["score"], slow_bad["score"]))
    floor = evaluate(par * 10, 4, n, max_mistakes=4)
    check(floor["score"] >= 100, "再差也有保底分：%d" % floor["score"])
    check(evaluate(par, 0, n)["stars"] == 3 and evaluate(par * 1.01, 0, n)["stars"] == 2,
          "目标用时是 3 星 / 2 星的分界（正好 par 算 3 星）")
    check(abs(par - (6.0 + 1.8 * n)) < 1e-6, "目标用时随箭头数线性增长：%.1fs" % par)


# ---------------------------------------------------------------- 2. 音效
def test_sound():
    print("\n== 音效接线 ==")
    rec = tempfile.mktemp(suffix=".json")
    game = Game(headless=True, mode="classic", records_path=rec)
    check(sound.preload() and sound.available, "音效加载成功（%d 个）" % len(sound.sounds))
    click_btn(game, game.btn_start)
    blocked = game.board.blocked_arrows()[0]
    click_cell(game, blocked.r, blocked.c)
    check(sound.last_played == "pick_bad", "点错 -> pick_bad（失败音效）")
    free = game.board.removable_arrows()[0]
    click_cell(game, free.r, free.c)
    check(sound.last_played == "pick_ok", "点对 -> pick_ok（鼓掌音效）")
    sound.toggle_mute()
    played = sound.play("pick_ok")
    check(sound.muted and played is False, "静音后不再出声")
    sound.toggle_mute()
    # 打通本关，检查通关音效
    finish_level(game)
    check(sound.last_played == "fireworks", "本关通关 -> fireworks（烟花音效）")
    pygame.quit()


# ---------------------------------------------------------------- 3. 关卡选项
def test_level_select():
    print("\n== 关卡选项界面 ==")
    rec = tempfile.mktemp(suffix=".json")
    game = Game(headless=True, mode="classic", records_path=rec)
    run_frames(game, 0.1)
    snap(game, "00_menu")
    click_btn(game, game.btn_more)
    check(game.state == Game.STATE_LEVELS, "菜单「更多关卡」-> 关卡选项界面")
    check(not load_records(rec).get("levels"), "新档案：还没有任何成绩记录")
    snap(game, "04_level_select_empty")
    rect = level_card_rect(3)
    game.on_click(rect.center)
    check(game.state == Game.STATE_PLAY and game.level_index == 3,
          "点第 4 关卡片 -> 直接进入第 %d 关（%s）" % (game.level_index + 1,
                                                game.levels[3].name))
    check(game.mode == "classic", "关卡选项进入的是固定关卡模式")
    snap(game, "level4_start")
    # 返回菜单按钮与随机挑战按钮
    game.state = Game.STATE_LEVELS
    click_btn(game, game.btn_back_lv)
    check(game.state == Game.STATE_MENU, "关卡选项「返回菜单」可用")
    click_btn(game, game.btn_more)
    click_btn(game, game.btn_random)
    check(game.state == Game.STATE_PLAY and game.mode == "random"
          and len(game.levels) == 5,
          "关卡选项「随机挑战」-> 现场生成 5 关（种子 %d）" % game.run_seed)
    pygame.quit()


# ---------------------------------------------------------------- 4. 记录与星级
def test_records_and_stars():
    print("\n== 成绩记录与星级结算 ==")
    rec = tempfile.mktemp(suffix=".json")
    game = Game(headless=True, mode="classic", records_path=rec)
    click_btn(game, game.btn_start)                 # 开始游戏 -> 经典第 1 关
    check(game.mode == "classic" and game.level_index == 0,
          "菜单「开始游戏」-> 固定 5 关的第 1 关")

    # 先故意点错一次：验证碰撞 + 失误 + 音效
    blocked = game.board.blocked_arrows()
    check(len(blocked) > 0, "第 1 关开局存在被挡箭头 %d 支" % len(blocked))
    a = blocked[0]
    before = game.board.mistakes_left
    click_cell(game, a.r, a.c)
    run_frames(game, 0.1, "01_crash", shot_at=3)
    check(game.board.mistakes_left == before - 1,
          "失误数 %d -> %d" % (before, game.board.mistakes_left))
    check(game.board.arrow_at(a.r, a.c) is a, "被挡箭头没有消失")
    v = game.view_of(a)
    check(v is not None and v.shake_t > 0, "碰撞箭头处于晃动动画中")

    layout_before = [lv.grid for lv in game.levels]
    click_btn(game, game.btn_restart)
    check(game.board.mistakes_left == game.board.max_mistakes and game.elapsed == 0.0,
          "重新开始：失误复原、计时归零")
    check([lv.grid for lv in game.levels] == layout_before, "重新开始不换布局")

    # 零失误通关 -> 3 星（自动测试点击几乎不耗时）
    finish_level(game, shot_prefix="03_flying")
    check(game.state == Game.STATE_CLEAR, "本关完成，进入结算界面")
    res = game.result
    check(res is not None and res["stars"] == 3,
          "零失误通关 -> %d 星 / %d 分（用时 %.1fs，目标 %.0fs）"
          % (res["stars"], res["score"], res["elapsed"], res["par"]))
    check(game.run_score == res["score"], "本局总分累计正确：%d" % game.run_score)
    rec_data = load_records(rec)
    check(str(0) in rec_data["levels"] and rec_data["levels"]["0"]["stars"] == 3,
          "最高分写入记录文件：%s" % rec_data["levels"].get("0"))
    snap(game, "05_clear_stars")

    # 第 2 关：故意失误 1 次 + 用时超过目标 -> 2 星
    click_btn(game, game.btn_next)
    check(game.level_index == 1, "进入第 2 关")
    b2 = game.board.blocked_arrows()[0]
    click_cell(game, b2.r, b2.c)
    game.elapsed = game.par_of_level(1) * 1.2       # 模拟“打了很久”
    finish_level(game)
    check(game.result["stars"] == 2, "失误 1 次且超时 -> %d 星（应为 2 星）"
          % game.result["stars"])

    # 用更差的成绩重打第 1 关，最高分不应被覆盖
    old = load_records(rec)["levels"]["0"]["score"]
    game.start_level(0)
    click_cell(game, *[(x.r, x.c) for x in game.board.blocked_arrows()][0])
    game.elapsed = game.par_of_level(0) * 3
    finish_level(game)
    check(load_records(rec)["levels"]["0"]["score"] == old,
          "更差的成绩不会覆盖最高分（仍为 %d）" % old)
    snap(game, "06_level_select_with_stars")

    # 结算界面星星动画的中间帧（对比 05_clear_stars 的最终状态）
    game.start_level(3)
    finish_level(game)
    snap(game, "07_clear_stars_anim")

    # 失败流程：不算分、不写记录
    print("\n== 失败流程 ==")
    game.start_level(4)
    while game.state == Game.STATE_PLAY:
        blocked = game.board.blocked_arrows()
        if not blocked:
            break
        a = blocked[0]
        click_cell(game, a.r, a.c)
        run_frames(game, 0.7)
    check(game.state == Game.STATE_FAIL, "失误耗尽后进入失败界面")
    check(game.result is None, "失败不计分（result 仍为空）")
    check(str(4) not in load_records(rec)["levels"], "失败不写入成绩记录")
    snap(game, "08_fail")
    click_btn(game, game.btn_back2)
    check(game.state == Game.STATE_LEVELS, "失败界面「返回菜单」回到关卡选项")
    snap(game, "09_level_select_final")
    pygame.quit()


# ---------------------------------------------------------------- 5. 自动试玩
def test_random_runs():
    print("\n== 随机关卡自动通关（%d 局 × 5 关）==" % RANDOM_RUNS)
    rec = tempfile.mktemp(suffix=".json")
    game = Game(headless=True, mode="random", records_path=rec)
    # 随机布局的生成可复现性
    a, sa = build_run(seed=20260919)
    b, sb = build_run(seed=20260919)
    c, _ = build_run(seed=20260920)
    check(sa == sb and [lv.grid for lv in a] == [lv.grid for lv in b],
          "同一种子生成完全相同的关卡布局")
    check([lv.grid for lv in a] != [lv.grid for lv in c], "不同种子生成不同布局")
    check(all(solve_level(lv) is not None for lv in a), "随机局每一关都可解")
    for lv in a:
        _ok, _order, blocked = analyze_specs(lv.arrow_specs(), lv.rows, lv.cols)
        check(blocked >= 1, "%dx%d 开局至少有 %d 支箭头被挡（有思考量）"
              % (lv.rows, lv.cols, blocked))

    for run in range(RANDOM_RUNS):
        game.new_run("random")
        check(len(game.levels) == 5, "第 %d 局生成 5 关（种子 %d）"
              % (run + 1, game.run_seed))
        for i in range(len(game.levels)):
            if i > 0:
                click_btn(game, game.btn_next)
            finish_level(game)
        check(game.state == Game.STATE_ALLCLEAR, "第 %d 局全部通关" % (run + 1))
        if run == 0:
            snap(game, "09_allclear_random")
    check(load_records(rec).get("levels") == {}, "随机关卡不写入经典关卡的成绩记录")
    pygame.quit()


def test_classic_allclear():
    print("\n== 经典 5 关连打 ==")
    rec = tempfile.mktemp(suffix=".json")
    game = Game(headless=True, mode="classic", records_path=rec)
    click_btn(game, game.btn_start)
    for i in range(len(game.levels)):
        if i > 0:
            click_btn(game, game.btn_next)
        finish_level(game)
        if i < len(game.levels) - 1:
            snap(game, "level%d_start" % (i + 2))
    check(game.state == Game.STATE_ALLCLEAR, "5 关全部清空 -> 全部通关界面")
    data = load_records(rec)
    check(len(data["levels"]) == 5, "5 关成绩全部写入记录（%d 条）" % len(data["levels"]))
    snap(game, "09_allclear_classic")
    pygame.quit()


def main():
    test_scoring()
    test_sound()
    test_level_select()
    test_records_and_stars()
    test_random_runs()
    test_classic_allclear()

    print("\n" + "=" * 50)
    if FAILED:
        print("有 %d 项失败：%s" % (len(FAILED), FAILED))
        sys.exit(1)
    print("全部测试通过 ✔  计分/星级/关卡选项/音效接线 + 随机关卡与经典关卡均实测通过。")


if __name__ == "__main__":
    main()
