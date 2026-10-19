"""
qbank.py - إدارة بنك الأسئلة المنهجية
"""

def get_questions_for_lesson(grade: str, subject: str, unit: int):
    return [
        {
            "id": 1,
            "question": "ما الفرق بين المفهوم النظري والتطبيق العملي في هذا الدرس؟",
            "answer": "المفهوم النظري يحدد القاعدة، بينما التطبيق يوضح استخدامها في المسائل اليومية."
        }
    ]
