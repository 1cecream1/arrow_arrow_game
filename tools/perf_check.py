# -*- coding: utf-8 -*-
"""
帧率实测：确认换成图片素材后动画依然流畅。

测三段最费时的场景，各跑若干帧，统计单帧耗时（update + draw + flip）：
  1. 菜单（自动演示小棋盘在动）
  2. 经典模式第 5 关（6×6 / 15 支箭头，画面元素最多）
  3. 连续飞出动画（每帧都在画飞行中的箭头）

用法：
    python tools/perf_check.py
"""
import os
import sys
import tempfile
import time

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

import pygame  # noqa: E402

from main import Game  # noqa: E402


def measure(label, step, frames):
    step()                                   # 预热一帧，避免把首次缓存计入
    times = []
    for _ in range(frames):
        t0 = time.perf_counter()
        step()
        times.append((time.perf_counter() - t0) * 1000.0)
    times.sort()
    avg = sum(times) / len(times)
    p95 = times[int(len(times) * 0.95)]
    print("%-28s 平均 %5.2f ms  中位 %5.2f ms  P95 %5.2f ms  -> 上限约 %3.0f FPS"
          % (label, avg, times[len(times) // 2], p95, 1000.0 / max(avg, 1e-6)))


def main():
    # 用临时成绩档案，避免性能测试往正式 records.json 里写入游玩记录
    game = Game(headless=True, mode="classic",
                records_path=os.path.join(tempfile.gettempdir(), "aa_perf_records.json"))
    game.state = Game.STATE_MENU

    def menu_step():
        game.update(1 / 60)
        game.draw()

    measure("菜单（自动演示动起来）", menu_step, 240)

    game.state = Game.STATE_LEVELS

    def levels_step():
        game.update(1 / 60)
        game.draw()

    measure("关卡选项（5 张卡片）", levels_step, 240)

    game.start_level(len(game.levels) - 1)   # 最后一关：画面元素最多

    def play_step():
        game.update(1 / 60)
        game.draw()

    measure("对局（6x6 / 15 支箭头）", play_step, 240)

    # 连续飞出：每 6 帧点一支可飞的箭头，让画面上一直有飞行中的箭头
    counter = {"n": 0}

    def fly_step():
        counter["n"] += 1
        if counter["n"] % 6 == 0:
            cand = game.board.removable_arrows()
            if cand:
                x, y = game.cell_center(cand[0].r, cand[0].c)
                game.on_click((x, y))
        game.update(1 / 60)
        game.draw()

    measure("连续飞出动画", fly_step, 300)
    print("\n注：dummy 驱动下是纯软件渲染，真机显卡合成只会更快；"
          "60 FPS 的单帧预算是 16.7 ms。")


if __name__ == "__main__":
    main()
