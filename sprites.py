# -*- coding: utf-8 -*-
"""
AIGC 素材的加载、朝向转换与缓存

素材来源：AI 生图（见 tools/prepare_assets.py 的预处理说明）
    assets/arrow.png     箭头（原图朝右，游戏内按方向旋转）
    assets/heart.png     爱心（HUD 剩余失误）
    assets/board_bg.png  界面背景底纹（已裁掉水印、柔化过）

为什么要有缓存：
    箭头每帧都要画，如果每次都现场旋转 + 缩放（smoothscale），一个棋盘
    十几支箭 × 60 帧就是上千次重采样，帧率会掉。这里把「旋转 + 缩放 + 变红」
    的结果按 (方向, 像素尺寸) 缓存下来，之后只做 blit，保证动画流畅。

素材缺失时（比如只拷贝了 .py 文件），自动退回程序绘制的箭头/爱心，
游戏依然可运行。
"""
import os

import pygame

ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

# AI 原图的箭头朝向（已用 tools/check_sprites.py 渲染验证：朝右）
BASE_DIR = "R"
# 从基准朝向旋转到各方向的角度（pygame 正角度 = 逆时针）
ROTATE = {"R": 0, "U": 90, "L": 180, "D": -90}

C_ARROW_FALLBACK = (44, 107, 209)
C_RED_FALLBACK = (225, 70, 75)


def _darker(color, k=0.78):
    return tuple(max(0, int(c * k)) for c in color)


def draw_arrow_proc(surface, cx, cy, size, direction, color=C_ARROW_FALLBACK):
    """程序绘制的箭头（素材缺失时的兜底）。"""
    from game_core import DELTA
    dr, dc = DELTA[direction]
    ux, uy = dc, dr
    px_, py_ = -uy, ux
    s = size * 0.74
    tip = (cx + ux * s * 0.52, cy + uy * s * 0.52)
    hb = (cx + ux * s * 0.08, cy + uy * s * 0.08)
    tail = (cx - ux * s * 0.46, cy - uy * s * 0.46)
    shaft_w = max(4, int(s * 0.28))
    head_w = s * 0.64
    h1 = (hb[0] + px_ * head_w / 2, hb[1] + py_ * head_w / 2)
    h2 = (hb[0] - px_ * head_w / 2, hb[1] - py_ * head_w / 2)
    pygame.draw.circle(surface, color, (int(tail[0]), int(tail[1])), shaft_w // 2)
    pygame.draw.line(surface, color, tail, hb, shaft_w)
    pygame.draw.polygon(surface, color, [tip, h1, h2])
    pygame.draw.polygon(surface, _darker(color), [tip, h1, h2], 2)


def draw_heart_proc(surface, cx, cy, size, color=C_RED_FALLBACK):
    """程序绘制的爱心（素材缺失时的兜底）。"""
    r = size * 0.25
    top = cy - size * 0.05
    pygame.draw.circle(surface, color, (int(cx - r), int(top)), int(r))
    pygame.draw.circle(surface, color, (int(cx + r), int(top)), int(r))
    pygame.draw.polygon(surface, color, [
        (cx - r * 1.92, top + r * 0.35),
        (cx + r * 1.92, top + r * 0.35),
        (cx, cy + size * 0.42),
    ])


class Sprites:
    def __init__(self, assets_dir=ASSETS_DIR):
        self.dir = assets_dir
        self.arrow_src = None
        self.heart_src = None
        self.bg_src = None
        self._loaded = False
        self._arrow_cache = {}
        self._flash_cache = {}
        self._heart_cache = {}
        self._bg_cache = {}

    def _load_file(self, name):
        path = os.path.join(self.dir, name)
        if not os.path.exists(path):
            return None                      # 素材缺失 -> 调用方退回程序绘制
        return pygame.image.load(path).convert_alpha()

    def preload(self):
        """在 pygame.display.set_mode() 之后调用，把三张素材读进内存。"""
        if self._loaded or pygame.display.get_surface() is None:
            return self._loaded
        self.arrow_src = self._load_file("arrow.png")
        self.heart_src = self._load_file("heart.png")
        self.bg_src = self._load_file("board_bg.png")
        self._loaded = True
        return True

    # ------------------------------------------------ 箭头
    def _arrow_shaped(self, direction, size, box_ratio=0.84):
        """
        旋转 + 等比缩放，把箭头放进 size × size 的方框里（占 box_ratio）。
        先按原图分辨率旋转（90° 倍数旋转无重采样损失），再 smoothscale 缩小，
        这样边缘比「先缩后旋」干净。
        """
        src = self.arrow_src
        sw, sh = src.get_size()
        rot = pygame.transform.rotate(src, ROTATE[direction])
        rw, rh = rot.get_size()
        scale = size * box_ratio / max(rw, rh)
        return pygame.transform.smoothscale(
            rot, (max(1, int(rw * scale)), max(1, int(rh * scale))))

    def arrow(self, direction, size):
        """返回该方向、该像素尺寸的箭头图片；素材缺失返回 None。"""
        if not self.preload() or self.arrow_src is None:
            return None
        key = (direction, size)
        if key not in self._arrow_cache:
            self._arrow_cache[key] = self._arrow_shaped(direction, size)
        return self._arrow_cache[key]

    def arrow_flash(self, direction, size):
        """
        碰撞用的“变红”版本。

        注意不能用「蓝色图 × 红色」的直接相乘：那样 G/B 被压掉后只剩近黑，
        看起来像变成深蓝而不是变红。正确做法是先取灰度（保留高光和透明边缘），
        再乘上红、并补一点红亮度，得到有立体感的红色箭头；
        叠加时按 flash 比例设置透明度，颜色就是平滑过渡而不是硬切。
        """
        if self.arrow(direction, size) is None:
            return None
        key = (direction, size)
        if key not in self._flash_cache:
            gray = pygame.transform.grayscale(self._arrow_cache[key])
            gray.fill((255, 62, 66), special_flags=pygame.BLEND_RGB_MULT)
            gray.fill((112, 0, 0), special_flags=pygame.BLEND_RGB_ADD)
            self._flash_cache[key] = gray
        return self._flash_cache[key]

    # ------------------------------------------------ 爱心
    def heart(self, size):
        if not self.preload() or self.heart_src is None:
            return None
        key = ("h", size)
        if key not in self._heart_cache:
            sw, sh = self.heart_src.get_size()
            scale = size / max(sw, sh)
            self._heart_cache[key] = pygame.transform.smoothscale(
                self.heart_src, (max(1, int(sw * scale)), max(1, int(sh * scale))))
        return self._heart_cache[key]

    def heart_empty(self, size):
        """已消耗的失误：同一张图去饱和 + 降透明度（不用额外生成素材）。"""
        if self.heart(size) is None:
            return None
        key = ("he", size)
        if key not in self._heart_cache:
            base = self._heart_cache[("h", size)].copy()
            base.fill((120, 122, 128, 105), special_flags=pygame.BLEND_RGBA_MULT)
            self._heart_cache[key] = base
        return self._heart_cache[key]

    # ------------------------------------------------ 背景底纹
    def backdrop(self, size):
        if not self.preload() or self.bg_src is None:
            return None
        if size not in self._bg_cache:
            self._bg_cache[size] = pygame.transform.smoothscale(self.bg_src, size)
        return self._bg_cache[size]


# 全局单例：其它模块直接用 sprites.arrow(...) / sprites.heart(...)
sprites = Sprites()
