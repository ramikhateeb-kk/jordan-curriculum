"""
slides.py - توليد الشرائح والعروض التقديمية للغرفة الصفية
"""

def generate_lesson_slides(title: str, objectives: list, steps: list, summary: str):
    return [
        {"slide": 1, "title": title, "content": "مرحباً بكم في درس اليوم - المنهاج الأردني"},
        {"slide": 2, "title": "أهداف التعلم", "bullets": objectives},
        {"slide": 3, "title": "الشرح والمفاهيم", "bullets": steps},
        {"slide": 4, "title": "الخلاصة والتكليف البيتي", "content": summary}
    ]
