"""
companion.py - المساعد الذكي لمرافقة الطالب في حل الواجبات
"""

from explain_ctx import explain_question_solution

def ask_companion(grade: str, subject: str, book_type: str, page: str, question: str, text: str = ""):
    return explain_question_solution(grade, subject, book_type, page, question, text)
