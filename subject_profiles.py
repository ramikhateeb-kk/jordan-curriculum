"""
subject_profiles.py - توصيف المواد الدراسية وخصائصها ومخرجات التعلم
"""

PROFILES = {
    "english": {
        "title": "Action Pack English Curriculum",
        "direction": "ltr",
        "focus_areas": ["Grammar", "Vocabulary", "Reading Comprehension", "Writing Skills", "Phonics"],
        "curriculum_standard": "CEFR aligned Jordanian standard"
    },
    "history": {
        "title": "منهاج التاريخ الأردني والعربي",
        "direction": "rtl",
        "focus_areas": ["حضارات الأردن", "الدولة الأموية والعباسية", "الثورة العربية الكبرى", "تاريخ الأردن المعاصر"],
        "curriculum_standard": "معايير وزارة التربية والتعليم للعلوم الإنسانية"
    },
    "science": {
        "title": "منهاج العلوم العامة وكيمياء/فيزياء/أحياء/علوم أرض",
        "direction": "rtl",
        "focus_areas": ["دورة الماء والغلاف المائي", "المادة وحالاتها", "القوة والحركة", "أجهزة جسم الإنسان"],
        "curriculum_standard": "الاستقصاء والتجارب العلمية المطورة"
    },
    "math": {
        "title": "منهاج الرياضيات المطور",
        "direction": "rtl",
        "focus_areas": ["الأعداد والعمليات", "الجبر والأنظمة الخطية", "حساب المثلثات", "الإحصاء والاحتمالات"],
        "curriculum_standard": "حل المشكلات والتفكير الرياضي"
    }
}

def get_profile(subject_key: str):
    return PROFILES.get(subject_key, PROFILES["science"])
