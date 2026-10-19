"""
profile_ctx.py - السياق الأكاديمي وملفات تقدم الطالب
"""

def get_student_context(student_id: str, grade: str):
    return {
        "student_id": student_id,
        "grade": grade,
        "strengths": ["Reading Comprehension", "العمليات الحسابية"],
        "needs_improvement": ["Grammar Tenses", "التحليل التاريخي"],
        "recommended_exercises_page": 24
    }
