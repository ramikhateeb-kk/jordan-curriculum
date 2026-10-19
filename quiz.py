"""
quiz.py - الاختبارات القصيرة الذاتية لطلبة المنهاج الأردني
"""

def generate_quick_quiz(grade: str, subject: str, topic: str):
    is_eng = "english" in subject.lower() or "action pack" in subject.lower()
    if is_eng:
        return {
            "title": f"Action Pack Quick Quiz - {topic}",
            "direction": "ltr",
            "questions": [
                {
                    "q": "Choose the correct past form: 'They _______ to the museum.'",
                    "options": ["go", "went", "gone", "going"],
                    "correct": "went"
                }
            ]
        }
    return {
        "title": f"اختبار قصير: {topic}",
        "direction": "rtl",
        "questions": [
            {
                "q": "اختر الإجابة الصحيحة وفق الكتاب المدرسي المقبول:",
                "options": ["الخيار أ", "الخيار ب", "الخيار ج"],
                "correct": "الخيار أ"
            }
        ]
    }
