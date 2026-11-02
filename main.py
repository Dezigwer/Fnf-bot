"""Точка входа. Запуск: python main.py (или run.bat / собранный .exe)."""

from __future__ import annotations

import ctypes
import io
import os
import sys
import traceback


def enable_dpi_awareness() -> None:
    """Без этого координаты при масштабе Windows 125/150% не совпадут с экраном."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def set_app_id() -> None:
    """Отдельная иконка/группа на панели задач, а не «python.exe»."""
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Fnf.Bot.1")
    except Exception:
        pass


def _report_crash(exc: BaseException) -> None:
    text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    try:
        from fnfbot import APP_DIR

        with open(os.path.join(APP_DIR, "error.log"), "a", encoding="utf-8") as fh:
            fh.write(text + "\n")
    except Exception:
        pass
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Ошибка запуска",
            "Не удалось запустить бота:\n\n" + str(exc) + "\n\nПодробности в error.log",
        )
        root.destroy()
    except Exception:
        pass


def _run_selftest() -> int:
    """Самопроверка. В одном .exe selftest.py лежит рядом внутри пакета."""
    frozen = bool(getattr(sys, "frozen", False))
    log_path = os.path.join(
        os.path.dirname(os.path.abspath(sys.executable if frozen else __file__)),
        "selftest.log",
    )

    if not frozen:
        import subprocess

        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "selftest.py")
        code = subprocess.call([sys.executable, script])
        return code

    base = getattr(sys, "_MEIPASS", "")
    script = os.path.join(base, "selftest.py")
    buffer = io.StringIO()
    code = 1
    try:
        source = open(script, "r", encoding="utf-8").read()
        namespace = {"__name__": "__main__", "__file__": script}
        with io.StringIO() as out:
            old_stdout, old_stderr = sys.stdout, sys.stderr
            sys.stdout = sys.stderr = out
            try:
                exec(compile(source, script, "exec"), namespace)
                code = 0
            except SystemExit as exc:
                code = int(exc.code or 0)
            finally:
                sys.stdout, sys.stderr = old_stdout, old_stderr
                buffer.write(out.getvalue())
    except Exception:
        buffer.write(traceback.format_exc())
        code = 1

    text = buffer.getvalue()
    try:
        with open(log_path, "w", encoding="utf-8") as fh:
            fh.write(text)
    except Exception:
        pass

    if "--quiet" not in sys.argv:
        try:
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()
            if code == 0:
                messagebox.showinfo(
                    "Самопроверка",
                    "Все проверки пройдены.\n\nПодробности: selftest.log рядом с exe.",
                )
            else:
                messagebox.showerror(
                    "Самопроверка",
                    "Есть ошибки. Подробности: selftest.log рядом с exe.",
                )
            root.destroy()
        except Exception:
            pass
    return code


def main() -> int:
    if "--selftest" in sys.argv:
        return _run_selftest()

    enable_dpi_awareness()
    set_app_id()
    try:
        from fnfbot.gui import run

        run()
        return 0
    except Exception as exc:  # noqa: BLE001
        _report_crash(exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
