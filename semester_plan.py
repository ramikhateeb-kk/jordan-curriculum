"""
semester_plan.py - الخطة الفصلية وتوزيع الحصص
"""

def get_semester_distribution(grade: str, subject: str, semester: int = 1):
    return {
        "grade": grade,
        "subject": subject,
        "semester": f"الفصل {semester}",
        "weeks": 16,
        "total_periods": 64
    }
