# -*- coding: utf-8 -*-
"""subject_profiles.py - توصيف المناهج والمباحث الدراسية الأردنية"""

SUBJECT_PROFILES = {
    "English": "Action Pack curriculum focused on communication, grammar, and literature.",
    "Math": "Collins curriculum focused on mathematical reasoning and problem-solving.",
    "Science": "Inquiry-based scientific exploration aligned with Collins textbooks."
}

def get_subject_profile(subject_name: str) -> str:
    return SUBJECT_PROFILES.get(subject_name, "منهاج معتمد من وزارة التربية والتعليم الأردنية.")
