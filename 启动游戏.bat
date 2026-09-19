# -*- coding: utf-8 -*-
# 双击即可启动游戏（使用本机 WorkBuddy 自带 Python 环境）
@echo off
chcp 65001 >nul
"C:\Users\m1781\.workbuddy\binaries\python\envs\default\Scripts\python.exe" "%~dp0main.py"
if errorlevel 1 pause
