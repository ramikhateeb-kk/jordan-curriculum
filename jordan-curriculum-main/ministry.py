# -*- coding: utf-8 -*-
"""exam.py, slides.py, ministry.py - خدمات الاختبارات والعروض التقديمية والوزارة"""

def get_ministry_guidelines() -> dict:
    return {
        "ministry": "وزارة التربية والتعليم",
        "guidelines": "الالتزام بجدول المواصفات ونتاجات التعلم الخاصة بكل مبحث."
    }

def generate_exam_paper(grade: str, subject: str, total_marks: int = 100) -> str:
    return f"نموذج امتحان مبحث {subject} - {grade} - الدرجة العظمى: {total_marks}"
