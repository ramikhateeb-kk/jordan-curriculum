# -*- coding: utf-8 -*-
"""qbank.py - إدارة بنك الأسئلة للمناهج الأردنية"""
from typing import List, Dict, Any

def get_questions_for_subject(grade: str, subject: str, unit: int = 1) -> List[Dict[str, Any]]:
    return [
        {
            "id": 1,
            "question": f"سؤال نموذجي لمادة {subject} - {grade}",
            "options": ["الخيار الأول", "الخيار الثاني", "الخيار الثالث", "الخيار الرابع"],
            "correct_index": 0,
            "explanation": "الشرح المعتمد وفق منهاج وزارة التربية والتعليم الأردنية."
        }
    ]
