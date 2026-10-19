"""
ministry.py - معايير وتعليمات وزارة التربية والتعليم الأردنية (MoE Jordan)
"""

MINISTRY_GUIDELINES = {
    "grading_system": {
        "first_assessment": 20,
        "second_assessment": 20,
        "activities_and_participation": 20,
        "final_exam": 40,
        "total": 100
    },
    "passing_grade": 50,
    "tawjihi_passing_grade": 50,
    "academic_calendar": {
        "semester_1_weeks": 16,
        "semester_2_weeks": 16,
        "holidays": ["عطلة ما بين الفصلين", "عيد الاستقلال 25 أيار", "عيد الفطر", "عيد الأضحى"]
    }
}

def get_ministry_guidelines():
    return MINISTRY_GUIDELINES
