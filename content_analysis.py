"""
content_analysis.py - تحليل المحتوى الدراسي وفق تصنيف بلوم والمعايير التربوية الأردنية
"""

from typing import Dict, List

def analyze_unit_content(subject: str, unit_name: str, grade: str) -> Dict[str, List[str]]:
    """
    تحليل محتوى الوحدة الدراسية إلى:
    - المفاهيم والمصطلحات
    - الحقائق والتعميمات
    - المهارات والعمليات
    - القيم والاتجاهات
    """
    is_eng = "english" in subject.lower() or "action pack" in subject.lower()
    
    if is_eng:
        return {
            "concepts": ["Verb tenses", "Punctuation marks", "Prefixes and Suffixes"],
            "skills": ["Reading for specific information", "Listening comprehension", "Writing a descriptive paragraph"],
            "values": ["Appreciating Jordanian heritage", "Environmental awareness", "Global citizenship"],
            "outcomes": [
                "Students will be able to use the Past Simple accurately in sentences.",
                "Students will acquire at least 15 new vocabulary items related to the unit."
            ]
        }
    else:
        return {
            "concepts": ["المفاهيم العلمية / اللغوية الأساسية", "المصطلحات والمفردات المركزية"],
            "skills": ["مهارة التحليل والمقارنة", "مهارة حل المسائل وتطبيق القوانين", "مهارة التعبير الكتابي"],
            "values": ["الاعتزاز بالهوية الوطنية الأردنية", "احترام التنوع الثقافي", "العمل الجماعي التعاوني"],
            "outcomes": [
                "أن يستنتج الطالب الفكرة الرئيسة للدرس والأفكار الفرعية بدقة.",
                "أن يحل تدريبات كتاب الأنشطة والتمارين المقررة."
            ]
        }
