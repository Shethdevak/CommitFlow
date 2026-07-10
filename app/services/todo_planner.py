"""Plans daily Redmine to-dos and distributes hours to hit the daily goal."""

from typing import List
from loguru import logger
from app.models.domain import ClassifiedCommit, WorkTodo

# Used when fewer than MIN_TODOS real commits exist
_SPLIT_TEMPLATES = [
    "Testing and verification: {msg}",
    "Review and follow-up: {msg}",
    "Documentation and cleanup: {msg}",
]


def split_hours(total: float, count: int) -> List[float]:
    """Split total hours into `count` parts that sum exactly to total (0.5h units when possible)."""
    if count <= 0:
        return []
    if count == 1:
        return [round(total, 2)]

    # Prefer half-hour increments
    units = int(round(total * 2))
    if units < count:
        # Fall back to finer (0.25h) units if needed
        units = int(round(total * 4))
        base = units // count
        rem = units % count
        hours = [((base + (1 if i < rem else 0)) / 4.0) for i in range(count)]
    else:
        base = units // count
        rem = units % count
        hours = [((base + (1 if i < rem else 0)) / 2.0) for i in range(count)]

    # Correct floating-point drift so sum == total
    drift = round(total - sum(hours), 2)
    if hours and drift != 0:
        hours[-1] = round(hours[-1] + drift, 2)
    return hours


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
        f"Changed files:\n{files}\n"
    )


class TodoPlannerService:
    """Builds daily to-dos from classified commits and allocates hours to the daily goal."""

    def __init__(self, daily_hour_goal: float = 8.0, min_todos: int = 3):
        self.daily_hour_goal = daily_hour_goal
        self.min_todos = max(1, min_todos)

    def plan(self, classified: List[ClassifiedCommit], date_str: str) -> List[WorkTodo]:
        """
        Rules:
        - If commit count >= min_todos → one to-do per commit
        - If commit count < min_todos → pad with synthetic follow-up to-dos
        - Hours always sum to daily_hour_goal across the whole day
        """
        if not classified:
            return []

        n = len(classified)
        todo_count = max(n, self.min_todos)
        hours = split_hours(self.daily_hour_goal, todo_count)
        todos: List[WorkTodo] = []

        # Real commit to-dos
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

        # Pad to min_todos using templates derived from existing commits
        pad_needed = todo_count - n
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
            f"(goal {self.daily_hour_goal}h)."
        )
        return todos
