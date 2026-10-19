# -*- coding: utf-8 -*-
"""marks_book.py - سجل العلامات والتقويم المدرسي المعتمد في الأردن"""
from typing import List, Dict, Any

def get_empty_marks_template() -> List[Dict[str, Any]]:
    return [
        {"student_name": "طالب تجريبي", "first_exam": 20, "second_exam": 20, "activities": 20, "final_exam": 40, "total": 100}
    ]
