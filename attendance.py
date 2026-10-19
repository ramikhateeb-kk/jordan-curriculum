"""
attendance.py - إدارة الحضور والغياب للطلبة وفق نماذج وزارة التربية والتعليم الأردنية
"""

import pandas as pd
from datetime import datetime

def generate_attendance_sheet(grade: str, section: str = "أ", student_count: int = 30) -> pd.DataFrame:
    """
    إنشاء جدول رصد الغياب المدرسي
    """
    students = [f"طالب {i+1}" for i in range(student_count)]
    df = pd.DataFrame({
        "الرقم": range(1, student_count + 1),
        "اسم الطالب": students,
        "الصف": [grade] * student_count,
        "الشعبة": [section] * student_count,
        "أيام الغياب بعذر": [0] * student_count,
        "أيام الغياب بدون عذر": [0] * student_count,
        "مجموع الغياب": [0] * student_count,
        "ملاحظات المرشد التربوي": [""] * student_count
    })
    return df

def calculate_attendance_rate(total_days: int, absent_days: int) -> float:
    if total_days <= 0:
        return 100.0
    attended = max(0, total_days - absent_days)
    return round((attended / total_days) * 100, 2)
