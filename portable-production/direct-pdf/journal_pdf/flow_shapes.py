from typing import Final

TERMINAL_LABELS: Final = frozenset({'开始', '结束', 'start', 'end'})


def is_flow_terminal(text: str, role: str | None = None) -> bool:
    return role in ('start', 'end') or text.strip().lower() in TERMINAL_LABELS
