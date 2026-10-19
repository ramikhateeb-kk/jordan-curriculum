"""
lesson_plan.py - إعداد خطط الدروس وفق نموذج وزارة التربية والتعليم الأردنية
"""

def generate_lesson_plan(grade: str, subject: str, unit_title: str):
    return {
        "grade": grade,
        "subject": subject,
        "unit": unit_title,
        "outcomes": [
            "أن يتعرف الطالب على المفاهيم الأساسية للدرس",
            "أن يحل تدريبات كتاب الطالب وكتاب الأنشطة بدقة"
        ],
        "strategies": ["الاستقصاء الموجه", "التفكير الناقد", "حل المشكلات"]
    }
