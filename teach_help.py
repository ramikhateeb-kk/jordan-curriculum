"""
teach_help.py - المساعد البيداغوجي للمعلم الأردني
"""

def get_teaching_strategy(topic_type: str) -> dict:
    strategies = {
        "grammar": {
            "name": "الاستقراء اللغوي والممارسة الموجهة (PPP)",
            "steps": ["Presentation (العرض)", "Practice (التدريب الموجه)", "Production (الإنتاج الحر)"]
        },
        "science": {
            "name": "دورة التعلم الخماسية (5E Model)",
            "steps": ["Engage (الانشغال)", "Explore (الاستكشاف)", "Explain (التفسير)", "Elaborate (التوسيع)", "Evaluate (التقويم)"]
        }
    }
    return strategies.get(topic_type, strategies["grammar"])
