"""Date utilities for calculating work days based on rotation schedule."""

from datetime import date, timedelta
from calendar import monthrange


# Anchor date: 2024-01-01 is Group A's work day
ANCHOR_DATE = date(2024, 1, 1)
ANCHOR_GROUP = "A"
CYCLE_LENGTH = 3  # 做一休二: work 1 day, rest 2 days

WEEKDAY_NAMES_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def get_group_offset(group_id: str) -> int:
    """Get the day offset for a group relative to Group A.

    Group A: offset 0 (works on anchor date)
    Group B: offset 1 (works day after A)
    Group C: offset 2 (works 2 days after A)
    """
    offsets = {"A": 0, "B": 1, "C": 2}
    return offsets.get(group_id.upper(), 0)


def is_work_day(target_date: date, group_id: str) -> bool:
    """Check if a given date is a work day for the specified group.

    Uses the anchor logic: 2024-01-01 is Group A's work day.
    Each group works every 3rd day in rotation.
    """
    days_since_anchor = (target_date - ANCHOR_DATE).days
    group_offset = get_group_offset(group_id)

    # Adjust for group offset and check if it falls on a work day
    adjusted_days = days_since_anchor - group_offset
    return adjusted_days % CYCLE_LENGTH == 0


def get_work_days_in_month(year: int, month: int, group_id: str) -> list[str]:
    """Get all work days for a group in a given month.

    Args:
        year: The year (e.g., 2024)
        month: The month (1-12)
        group_id: The group identifier ("A", "B", or "C")

    Returns:
        List of date strings in "YYYY-MM-DD" format
    """
    work_days = []
    _, days_in_month = monthrange(year, month)

    for day in range(1, days_in_month + 1):
        current_date = date(year, month, day)
        if is_work_day(current_date, group_id):
            work_days.append(current_date.strftime("%Y-%m-%d"))

    return work_days


def get_day_of_week_cn(date_str: str) -> str:
    """Get Chinese day of week name for a date string.

    Args:
        date_str: Date in "YYYY-MM-DD" format

    Returns:
        Chinese weekday name (周一, 周二, etc.)
    """
    parts = date_str.split("-")
    d = date(int(parts[0]), int(parts[1]), int(parts[2]))
    return WEEKDAY_NAMES_CN[d.weekday()]


def parse_month(month_str: str) -> tuple[int, int]:
    """Parse a month string into year and month.

    Args:
        month_str: Month in "YYYY-MM" format

    Returns:
        Tuple of (year, month)
    """
    parts = month_str.split("-")
    return int(parts[0]), int(parts[1])


def generate_work_days_from_first_day(year: int, month: int, first_day: int) -> list[str]:
    """从首个工作日生成整月工作日列表（间隔2天）

    Args:
        year: 年份
        month: 月份
        first_day: 首个工作日（1-31）

    Returns:
        工作日列表，格式 ["YYYY-MM-DD", ...]

    Example:
        generate_work_days_from_first_day(2026, 1, 1) -> ["2026-01-01", "2026-01-04", "2026-01-07", ...]
    """
    work_days = []
    _, days_in_month = monthrange(year, month)

    current_day = first_day
    while current_day <= days_in_month:
        work_days.append(date(year, month, current_day).strftime("%Y-%m-%d"))
        current_day += 3  # 间隔2天，即每3天一个工作日

    return work_days
