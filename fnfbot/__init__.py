"""Fnf-bot — оверлейный бот-плеер для FNF (Roblox и не только).

Работает без внедрения в игру: захватывает экран, ищет изменение пикселей
в заданной области ноты и нажимает назначенную клавишу.
"""

import os
import sys

if getattr(sys, "frozen", False):
    # В одном .exe настройки и скриншоты лежат рядом с самим exe, а не во временной папке.
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Ресурсы, упакованные внутрь exe (иконка и т. п.).
RESOURCE_DIR = getattr(sys, "_MEIPASS", APP_DIR)

__version__ = "1.3.1"
