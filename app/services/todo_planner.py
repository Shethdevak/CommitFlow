"""Plans daily Redmine to-dos and distributes hours by commit effort (not equally)."""

import math
import re
from typing import List, Sequence
from loguru import logger
from app.models.domain import ClassifiedCommit, Commit, WorkTodo

# Used when fewer than MIN_TODOS real commits exist
_SPLIT_TEMPLATES = [
    "Testing and verification: {msg}",
    "Review and follow-up: {msg}",
    "Documentation and cleanup: {msg}",
]

# Conventional-commit / message hints → effort multiplier
_TYPE_WEIGHTS = [
    (re.compile(r"^(feat|feature)(\(.*\))?:", re.I), 1.4),
    (re.compile(r"^refactor(\(.*\))?:", re.I), 1.3),
    (re.compile(r"^(perf|performance)(\(.*\))?:", re.I), 1.2),
    (re.compile(r"^fix(\(.*\))?:", re.I), 0.85),
    (re.compile(r"^(docs|chore|style|ci|build|test)(\(.*\))?:", re.I), 0.55),
]

_SMALL_HINT = re.compile(
    r"\b(typo|typos|quick\s*fix|minor|hotfix|trivial|cleanup|lint|format|whitespace|wip)\b",
    re.I,
)
_LARGE_HINT = re.compile(
    r"\b(implement|introduce|overhaul|migrate|redesign|architecture|integration)\b",
    re.I,
)


def score_commit(commit: Commit) -> float:
    """
    Estimate relative effort for a commit (higher = more hours).

    Signals a senior would use:
    - lines changed (additions + deletions)
    - number of files touched
    - commit type (feat/refactor vs chore/docs/quick fix)
    """
    lines = max(0, int(commit.additions) + int(commit.deletions))
    files = max(0, len(commit.changed_files))
    msg = (commit.message or "").strip()

    # Diminishing returns so one huge commit doesn't eat the whole day alone
    line_score = math.log1p(lines) * 2.2
    file_score = math.log1p(files) * 1.6

    type_mult = 1.0
    for pattern, mult in _TYPE_WEIGHTS:
        if pattern.search(msg):
            type_mult = mult
            break

    if _SMALL_HINT.search(msg):
        type_mult *= 0.45
    elif _LARGE_HINT.search(msg):
        type_mult *= 1.15

    # Bare minimum so empty-stat commits still get some weight
    raw = (line_score + file_score + 0.75) * type_mult
    return max(0.35, raw)


def allocate_hours_by_weights(
    total: float,
    weights: Sequence[float],
    *,
    min_hours: float | None = None,
) -> List[float]:
    """
    Distribute `total` hours by relative weights using 0.5h (or 0.25h) units.
    Every item gets at least `min_hours` when the budget allows.

    When many to-dos share one day, the floor drops automatically so large
    features can still receive a clearly larger share than quick fixes.
    """
    n = len(weights)
    if n == 0:
        return []
    if n == 1:
        return [round(total, 2)]

    if min_hours is None:
        # Reserve at most ~55% of the day as floors so weights still matter
        if n * 0.5 <= total * 0.55:
            min_hours = 0.5
        elif n * 0.25 <= total * 0.55:
            min_hours = 0.25
        else:
            min_hours = 0.25

    units_total = int(round(total * 2))  # half-hour units
    min_units = max(1, int(round(min_hours * 2)))

    # If we can't give everyone the minimum in 0.5h steps, drop to 0.25h
    if units_total < n * min_units or min_hours < 0.5:
        return _allocate_quarter_hours(total, weights, min_hours=min(min_hours, 0.25))

    # Reserve minimum for each, distribute the rest by weight
    remaining_units = units_total - (n * min_units)
    safe_weights = [max(0.01, float(w)) for w in weights]
    weight_sum = sum(safe_weights)

    # Largest-remainder method for fair integer extras
    exact = [(remaining_units * w / weight_sum) for w in safe_weights]
    floors = [int(math.floor(x)) for x in exact]
    assigned = sum(floors)
    leftovers = remaining_units - assigned
    order = sorted(
        range(n),
        key=lambda i: (exact[i] - floors[i], safe_weights[i]),
        reverse=True,
    )
    for i in order[:leftovers]:
        floors[i] += 1

    hours = [round((min_units + floors[i]) / 2.0, 2) for i in range(n)]
    drift = round(total - sum(hours), 2)
    if hours and drift != 0:
        heaviest = max(range(n), key=lambda i: safe_weights[i])
        hours[heaviest] = round(hours[heaviest] + drift, 2)
    return hours


def _allocate_quarter_hours(
    total: float,
    weights: Sequence[float],
    *,
    min_hours: float = 0.25,
) -> List[float]:
    n = len(weights)
    units_total = int(round(total * 4))
    min_units = max(1, int(round(min_hours * 4)))
    if units_total < n:
        # Absolute fallback: at least 1 unit each if possible
        base = [1] * n
        while sum(base) > units_total and any(u > 0 for u in base):
            for i in range(n):
                if sum(base) <= units_total:
                    break
                if base[i] > 0:
                    base[i] -= 1
        hours = [u / 4.0 for u in base]
    else:
        remaining = units_total - n * min_units
        if remaining < 0:
            remaining = 0
            min_units = max(1, units_total // n)
        safe_weights = [max(0.01, float(w)) for w in weights]
        weight_sum = sum(safe_weights)
        exact = [(remaining * w / weight_sum) for w in safe_weights]
        floors = [int(math.floor(x)) for x in exact]
        leftovers = remaining - sum(floors)
        order = sorted(range(n), key=lambda i: exact[i] - floors[i], reverse=True)
        for i in order[: max(0, leftovers)]:
            floors[i] += 1
        hours = [round((min_units + floors[i]) / 4.0, 2) for i in range(n)]

    drift = round(total - sum(hours), 2)
    if hours and drift != 0:
        heaviest = max(range(n), key=lambda i: weights[i])
        hours[heaviest] = round(hours[heaviest] + drift, 2)
    return hours


def split_hours(total: float, count: int) -> List[float]:
    """Equal split helper (kept for tests / simple callers). Prefer allocate_hours_by_weights."""
    if count <= 0:
        return []
    return allocate_hours_by_weights(total, [1.0] * count)


def _commit_description(item: ClassifiedCommit, date_str: str) -> str:
    c = item.commit
    files = "\n".join(f"- {f}" for f in c.changed_files[:20]) or "- (no file list)"
    url = c.url or "N/A"
    return (
        f"Date: {date_str}\n"
        f"Repository: {c.repository}\n"
        f"Feature: {item.feature_name}\n"
        f"Commit: {c.hash[:10]}\n"
        f"URL: {url}\n\n"
        f"Message:\n{c.message}\n\n"
        f"Stats: +{c.additions} / -{c.deletions}, {len(c.changed_files)} file(s)\n\n"
        f"Changed files:\n{files}\n"
    )


class TodoPlannerService:
    """Builds daily to-dos from classified commits and allocates hours by effort."""

    def __init__(self, daily_hour_goal: float = 8.0, min_todos: int = 3):
        self.daily_hour_goal = daily_hour_goal
        self.min_todos = max(1, min_todos)

    def plan(self, classified: List[ClassifiedCommit], date_str: str) -> List[WorkTodo]:
        """
        Rules:
        - If commit count >= min_todos → one to-do per commit
        - If commit count < min_todos → pad with synthetic follow-up to-dos (low weight)
        - Hours sum to daily_hour_goal, weighted by commit effort (not equal)
        """
        if not classified:
            return []

        n = len(classified)
        todo_count = max(n, self.min_todos)
        pad_needed = todo_count - n

        weights: List[float] = [score_commit(item.commit) for item in classified]
        # Synthetic follow-ups are real work but lighter than the main implementation
        for _ in range(pad_needed):
            source_weight = weights[_ % n] if n else 1.0
            weights.append(max(0.4, source_weight * 0.35))

        hours = allocate_hours_by_weights(self.daily_hour_goal, weights)
        todos: List[WorkTodo] = []

        for i, item in enumerate(classified):
            todos.append(
                WorkTodo(
                    subject=item.commit.message[:255],
                    description=_commit_description(item, date_str),
                    hours=hours[i],
                    project_id=item.project_id,
                    project_name=item.project_name,
                    feature_name=item.feature_name,
                    parent_issue_id=item.parent_issue_id,
                    commits=[item.commit],
                    is_synthetic=False,
                )
            )
            logger.info(
                f"Hour weight for {item.commit.hash[:8]} "
                f"(+{item.commit.additions}/-{item.commit.deletions}, "
                f"{len(item.commit.changed_files)} files, "
                f"msg={item.commit.message[:50]!r}): "
                f"weight={weights[i]:.2f} → {hours[i]}h"
            )

        for pad_idx in range(pad_needed):
            source = classified[pad_idx % n]
            template = _SPLIT_TEMPLATES[pad_idx % len(_SPLIT_TEMPLATES)]
            subject = template.format(msg=source.commit.message)[:255]
            hour_index = n + pad_idx
            todos.append(
                WorkTodo(
                    subject=subject,
                    description=(
                        f"Supporting work for: {source.commit.message}\n\n"
                        + _commit_description(source, date_str)
                    ),
                    hours=hours[hour_index],
                    project_id=source.project_id,
                    project_name=source.project_name,
                    feature_name=source.feature_name,
                    parent_issue_id=source.parent_issue_id,
                    commits=[source.commit],
                    is_synthetic=True,
                )
            )

        total = round(sum(t.hours for t in todos), 2)
        logger.info(
            f"Planned {len(todos)} to-dos for {date_str} "
            f"({n} commit(s), {pad_needed} synthetic) totaling {total}h "
            f"(goal {self.daily_hour_goal}h) using effort-weighted hours."
        )
        return todos
