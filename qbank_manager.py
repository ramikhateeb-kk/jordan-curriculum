"""
qbank_manager.py - إدارة بنك الأسئلة وفق مستويات التفكير (تذكر، فهم، تطبيق، تحليل، تركيب، تقويم)
"""

from typing import List, Dict

def filter_questions(grade: str, subject: str, difficulty: str = "medium", taxonomy: str = "تطبيق") -> List[Dict]:
    return [
        {
            "id": "Q101",
            "grade": grade,
            "subject": subject,
            "taxonomy": taxonomy,
            "difficulty": difficulty,
            "question": "وضح بالخطوات كيفية استخراج النتيجة وفق القاعدة المقررة.",
            "answer": "تطبيق الخطوة الأولى واستنتاج الناتج النهائي مباشرة مع التعليل."
        }
    ]
