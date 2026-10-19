"""
catalog.py - فهرس كتب ومواد المنهاج الأردني المطور لكافة الصفوف
"""

JORDAN_CURRICULUM_CATALOG = {
    "grades": [
        "الصف الأول الأساسي",
        "الصف الثاني الأساسي",
        "الصف الثالث الأساسي",
        "الصف الرابع الأساسي",
        "الصف الخامس الأساسي",
        "الصف السادس الأساسي",
        "الصف السابع الأساسي",
        "الصف الثامن الأساسي",
        "الصف التاسع الأساسي",
        "الصف العاشر الأساسي",
        "الأول ثانوي (الحادي عشر)",
        "الثاني ثانوي (التوجيهي)"
    ],
    "subjects": [
        {"id": "english", "name": "اللغة الإنجليزية (Action Pack)", "is_english": True},
        {"id": "math", "name": "الرياضيات", "is_english": False},
        {"id": "science", "name": "العلوم العامة المطورة", "is_english": False},
        {"id": "history", "name": "التاريخ", "is_english": False},
        {"id": "geography", "name": "الجغرافيا", "is_english": False},
        {"id": "arabic", "name": "اللغة العربية", "is_english": False},
        {"id": "islamic", "name": "التربية الإسلامية", "is_english": False}
    ],
    "book_types": [
        "كتاب الطالب (Student Book)",
        "كتاب الأنشطة والتمارين (Activity Book)"
    ]
}

def get_catalog():
    return JORDAN_CURRICULUM_CATALOG
