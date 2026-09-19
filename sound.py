# -*- coding: utf-8 -*-
"""
音效播放（pygame.mixer）

素材：assets/sounds/*.wav，由 tools/make_sounds.py 用 Python 标准库现场合成
      （不下载第三方音频，避免版权问题）。

    pick_ok.wav      正确选择（箭头飞出）—— 掌声
    pick_bad.wav     错误选择（被挡住）—— 下行低鸣
    level_clear.wav  通关 —— 上行琶音
    fireworks.wav    全部通关 —— 烟花（引信 + 爆响 + 噼啪）

设计要点：
  - 没有声卡 / 素材缺失 / 混音器初始化失败时自动静默降级，绝不影响游戏运行；
  - 每次播放都会记在 `last_played` 上，自动测试不用听声音也能验证音效接线是否正确。
"""
import os

import pygame

SOUND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "sounds")
NAMES = ("pick_ok", "pick_bad", "level_clear", "fireworks")
# 各音效的响度平衡（合成时 RMS 差异较大，这里统一听感）
GAIN = {"pick_ok": 0.85, "pick_bad": 0.80, "level_clear": 0.60, "fireworks": 0.95}


class SoundBank:
    def __init__(self, sound_dir=SOUND_DIR):
        self.dir = sound_dir
        self.sounds = {}
        self.muted = False
        self.available = False
        self._loaded = False
        self.last_played = None      # 供自动测试断言

    def preload(self):
        """初始化混音器并载入音效；任何一步失败都安静返回 False。"""
        if self._loaded:
            return self.available
        self._loaded = True
        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
        except pygame.error:
            return False
        for name in NAMES:
            path = os.path.join(self.dir, name + ".wav")
            if not os.path.exists(path):
                continue
            try:
                snd = pygame.mixer.Sound(path)
                snd.set_volume(GAIN.get(name, 1.0))
                self.sounds[name] = snd
            except pygame.error:
                pass
        self.available = bool(self.sounds)
        return self.available

    def play(self, name):
        """播放音效；返回是否真的出声（静音/无素材/无设备都返回 False）。"""
        self.last_played = name
        if self.muted or not self.preload():
            return False
        snd = self.sounds.get(name)
        if snd is None:
            return False
        try:
            snd.play()
            return True
        except pygame.error:
            return False

    def toggle_mute(self):
        self.muted = not self.muted
        return self.muted


# 全局单例：其它模块直接用 sound.play("pick_ok")
sound = SoundBank()
