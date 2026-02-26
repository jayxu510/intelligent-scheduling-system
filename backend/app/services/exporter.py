"""Excel export service for schedule data."""

import io
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

from app.models.schemas import (
    Employee,
    ShiftType,
    DailySchedule,
)


# Color scheme for shift types
SHIFT_COLORS = {
    ShiftType.DAY: "FFF3E0",        # Light orange
    ShiftType.SLEEP: "E3F2FD",       # Light blue
    ShiftType.MINI_NIGHT: "F3E5F5",  # Light purple
    ShiftType.LATE_NIGHT: "FCE4EC",  # Light pink
    ShiftType.VACATION: "E8F5E9",    # Light green
    ShiftType.NONE: "FAFAFA",        # Light gray
}

SHIFT_LABELS = {
    ShiftType.DAY: "白",
    ShiftType.SLEEP: "睡",
    ShiftType.MINI_NIGHT: "小夜",
    ShiftType.LATE_NIGHT: "大夜",
    ShiftType.VACATION: "休",
    ShiftType.NONE: "",
}


def export_schedule_to_excel(
    month: str,
    group_id: str,
    schedules: list[DailySchedule],
    employees: list[Employee],
) -> io.BytesIO:
    """Export schedule to Excel file.

    Args:
        month: Month string (e.g., "2024-10")
        group_id: Group identifier (A, B, or C)
        schedules: List of daily schedules
        employees: List of employees

    Returns:
        BytesIO buffer containing the Excel file
    """
    wb = Workbook()
    ws = wb.active
    ws.title = f"{month} {group_id}组排班表"

    # Styles
    header_font = Font(bold=True, size=12)
    header_fill = PatternFill(start_color="4A90D9", end_color="4A90D9", fill_type="solid")
    header_font_white = Font(bold=True, size=12, color="FFFFFF")
    center_align = Alignment(horizontal="center", vertical="center")
    thin_border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )

    # Build employee lookup
    emp_by_id = {e.id: e for e in employees}

    # Header row
    ws.cell(row=1, column=1, value="日期").font = header_font_white
    ws.cell(row=1, column=1).fill = header_fill
    ws.cell(row=1, column=1).alignment = center_align
    ws.cell(row=1, column=1).border = thin_border

    ws.cell(row=1, column=2, value="星期").font = header_font_white
    ws.cell(row=1, column=2).fill = header_fill
    ws.cell(row=1, column=2).alignment = center_align
    ws.cell(row=1, column=2).border = thin_border

    # Employee name headers
    for col, emp in enumerate(employees, start=3):
        cell = ws.cell(row=1, column=col, value=emp.name)
        cell.font = header_font_white
        cell.fill = header_fill
        cell.alignment = center_align
        cell.border = thin_border

    # Data rows
    for row_idx, schedule in enumerate(schedules, start=2):
        # Date column
        date_cell = ws.cell(row=row_idx, column=1, value=schedule.date)
        date_cell.alignment = center_align
        date_cell.border = thin_border

        # Day of week column
        dow_cell = ws.cell(row=row_idx, column=2, value=schedule.day_of_week)
        dow_cell.alignment = center_align
        dow_cell.border = thin_border

        # Build record lookup for this day
        record_by_emp = {r.employee_id: r for r in schedule.records}

        # Employee shift cells
        for col, emp in enumerate(employees, start=3):
            record = record_by_emp.get(emp.id)
            shift_type = record.shift_type if record else ShiftType.NONE

            cell = ws.cell(row=row_idx, column=col, value=SHIFT_LABELS.get(shift_type, ""))
            cell.alignment = center_align
            cell.border = thin_border

            # Apply color
            color = SHIFT_COLORS.get(shift_type, "FFFFFF")
            cell.fill = PatternFill(start_color=color, end_color=color, fill_type="solid")

    # Adjust column widths
    ws.column_dimensions[get_column_letter(1)].width = 12  # Date
    ws.column_dimensions[get_column_letter(2)].width = 8   # Day of week
    for col in range(3, len(employees) + 3):
        ws.column_dimensions[get_column_letter(col)].width = 6

    # Add summary sheet
    _add_summary_sheet(wb, month, group_id, schedules, employees)

    # Save to buffer
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    return buffer


def _add_summary_sheet(
    wb: Workbook,
    month: str,
    group_id: str,
    schedules: list[DailySchedule],
    employees: list[Employee],
):
    """Add a summary statistics sheet to the workbook."""
    ws = wb.create_sheet(title="统计")

    # Styles
    header_font = Font(bold=True, size=11)
    header_fill = PatternFill(start_color="E0E0E0", end_color="E0E0E0", fill_type="solid")
    center_align = Alignment(horizontal="center", vertical="center")
    thin_border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )

    emp_by_id = {e.id: e for e in employees}

    # Calculate statistics
    shift_counts = {emp.id: {st: 0 for st in ShiftType} for emp in employees}

    for schedule in schedules:
        for record in schedule.records:
            if record.employee_id in shift_counts:
                shift_counts[record.employee_id][record.shift_type] += 1

    # Headers
    headers = ["姓名", "白班", "睡觉班", "小夜班", "大夜班", "休假", "总计"]
    for col, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align
        cell.border = thin_border

    # Data rows
    for row_idx, emp in enumerate(employees, start=2):
        counts = shift_counts[emp.id]

        ws.cell(row=row_idx, column=1, value=emp.name).border = thin_border
        ws.cell(row=row_idx, column=2, value=counts[ShiftType.DAY]).border = thin_border
        ws.cell(row=row_idx, column=3, value=counts[ShiftType.SLEEP]).border = thin_border
        ws.cell(row=row_idx, column=4, value=counts[ShiftType.MINI_NIGHT]).border = thin_border
        ws.cell(row=row_idx, column=5, value=counts[ShiftType.LATE_NIGHT]).border = thin_border
        ws.cell(row=row_idx, column=6, value=counts[ShiftType.VACATION]).border = thin_border

        total = sum(counts.values()) - counts[ShiftType.NONE]
        ws.cell(row=row_idx, column=7, value=total).border = thin_border

        for col in range(1, 8):
            ws.cell(row=row_idx, column=col).alignment = center_align

    # Adjust column widths
    ws.column_dimensions["A"].width = 10
    for col in range(2, 8):
        ws.column_dimensions[get_column_letter(col)].width = 10
