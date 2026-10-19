"""
reading_texts.py - نصوص القراءة والاستيعاب لمناهج اللغة الإنجليزية والعربية
"""

ACTION_PACK_TEXTS = {
    "grade_4_unit_3": {
        "title": "A Visit to Jerash and Amman Citadel",
        "direction": "ltr",
        "text": """Last week, Kareem and his family visited Jerash. Jerash is an ancient Roman city in the north of Jordan. 
They saw the tall columns, the South Theatre, and the Oval Plaza. Kareem took photos of the stone arches. 
Later, they returned to Amman and explored the Citadel at sunset. It was a wonderful journey into history.""",
        "vocabulary": [
            {"word": "Columns", "meaning": "أعمدة أثرية"},
            {"word": "Citadel", "meaning": "قلعة تاريخية"},
            {"word": "Arches", "meaning": "أقواس حجرية"}
        ]
    }
}

def get_reading_text(unit_key: str):
    return ACTION_PACK_TEXTS.get(unit_key, ACTION_PACK_TEXTS["grade_4_unit_3"])
