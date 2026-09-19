# -*- coding: utf-8 -*-
"""
素材朝向自检：把四个方向的箭头与爱心渲染成一张对照图，人眼确认方向映射正确。

用法：
    python tools/check_sprites.py
输出：
    screenshots/_sprite_check.png
"""
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

import pygame  # noqa: E402

from sprites import sprites, draw_arrow_proc, draw_heart_proc  # noqa: E402


def main():
    pygame.init()
    screen = pygame.display.set_mode((1000, 420))
    screen.fill((246, 248, 251))
    font = pygame.font.Font("C:/Windows/Fonts/msyh.ttc", 22)

    # 四方向箭头（图片素材）
    for i, (d, name) in enumerate([("U", "上"), ("D", "下"), ("L", "左"), ("R", "右")]):
        cx = 120 + i * 150
        img = sprites.arrow(d, 130)
        if img:
            screen.blit(img, img.get_rect(center=(cx, 120)))
        else:
            draw_arrow_proc(screen, cx, 120, 130, d)
        label = font.render("%s (%s)" % (d, name), True, (60, 70, 85))
        screen.blit(label, (cx - label.get_width() / 2, 200))

    # 爱心：满 / 空 / 兜底
    h1 = sprites.heart(64)
    h2 = sprites.heart_empty(64)
    if h1:
        screen.blit(h1, h1.get_rect(center=(780, 110)))
        screen.blit(h2, h2.get_rect(center=(870, 110)))
    else:
        draw_heart_proc(screen, 780, 110, 64)
    screen.blit(font.render("满 / 空", True, (60, 70, 85)), (790, 160))

    # 兜底绘制（素材缺失时用）
    draw_arrow_proc(screen, 200, 320, 90, "R", (150, 160, 175))
    draw_heart_proc(screen, 320, 320, 60, (180, 185, 195))
    screen.blit(font.render("素材缺失时的兜底绘制", True, (150, 160, 175)), (400, 310))

    path = os.path.join(BASE, "screenshots", "_sprite_check.png")
    pygame.image.save(screen, path)
    print("已输出 %s" % path)
    pygame.quit()


if __name__ == "__main__":
    main()
