# -*- coding: utf-8 -*-
"""semester_plan.py - إعداد وتوزيع الخطة الفصلية للمنهاج الأردني"""

def generate_semester_plan(grade: str, subject: str, semester: str = "الفصل الأول") -> str:
    return f"""
الخطة الفصلية المعتمدة - وزارة التربية والتعليم الأردنية
المادة: {subject} | الصف: {grade} | {semester}
عدد الأسابيع التدريسية: 16 أسبوعاً
توزيع الوحدات ونتاجات التعلم والتقويم المعتمد.
""".strip()
