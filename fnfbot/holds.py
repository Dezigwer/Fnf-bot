"""Логика удержания клавиши для слайдов (hold-нот).

Отдельный класс без зависимостей от экрана: движок спрашивает «отпускать уже?»,
а тесты могут прогнать любую последовательность времени и состояний.

Как это работает
----------------
1. Нота пришла в приёмник — движок жмёт клавишу.
2. Пока в области приёмника что-то есть (нота или хвост слайдера) — держим.
3. Область опустела и молчит `grace_ms` — слайд закончился, отпускаем.
4. Если нота исчезла почти сразу (короче `tail_confirm_ms`) — это обычный тап:
   отпускаем через `tap_ms`, как раньше.
5. Страховка `max_ms` — чтобы клавиша не залипла, если игра свернулась
   или в области остался шум.

Важно: сигнал берётся из области приёмника, а не из полосы над ним. Через полосу
над приёмником проходят все падающие ноты, и удержание по ней зажимало клавиши
на всю песню — после этого игра перестаёт видеть новые нажатия.
"""

from __future__ import annotations


class HoldController:
    """Решает, когда отпустить клавишу после нажатия."""

    def __init__(
        self,
        enabled: bool = True,
        tap_ms: int = 30,
        grace_ms: int = 80,
        max_ms: int = 8000,
        tail_confirm_ms: int = 90,
    ):
        self.enabled = bool(enabled)
        self.tap_ms = max(1, int(tap_ms))
        self.grace_ms = max(10, int(grace_ms))
        self.max_ms = max(50, int(max_ms))
        self.tail_confirm_ms = max(20, int(tail_confirm_ms))

        self.active = False
        self.seen_tail = False
        self._pressed_at = 0.0
        self._last_signal = 0.0

    # --- события ---
    def on_press(self, now: float, note_present: bool = True) -> None:
        self.active = True
        self.seen_tail = False
        self._pressed_at = now
        self._last_signal = now if note_present else 0.0

    def reset(self) -> None:
        self.active = False
        self.seen_tail = False
        self._pressed_at = 0.0
        self._last_signal = 0.0

    def held_for(self, now: float) -> float:
        """Сколько клавиша держится, секунд."""
        return max(0.0, now - self._pressed_at)

    def update(self, now: float, note_present: bool) -> bool:
        """True — пора отпускать клавишу."""
        if not self.active:
            return False

        held = now - self._pressed_at
        if held >= self.max_ms / 1000.0:
            return True

        # Слайды выключены — обычный тап фиксированной длины.
        if not self.enabled:
            return held >= self.tap_ms / 1000.0

        if note_present:
            self._last_signal = now
            if held >= self.tail_confirm_ms / 1000.0:
                self.seen_tail = True
            return False

        if self.seen_tail:
            # Хвост закончился: ждём короткую тишину, чтобы не сорваться на мигании.
            return (now - self._last_signal) >= self.grace_ms / 1000.0

        # Короткая нота: пара кадров тишины и отпускаем.
        return (now - max(self._last_signal, self._pressed_at)) >= self.tap_ms / 1000.0
