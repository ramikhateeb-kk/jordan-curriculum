"""
marks_book.py - سجل العلامات المدرسي المعتمد (دفتر العلامات الجانبي)
"""

import pandas as pd

def create_gradebook_template(grade: str, subject: str, student_names: list = None) -> pd.DataFrame:
    """
    إنشاء جدول رصد علامات الفترات الأربع المعتمد في المدارس الأردنية:
    - التقويم الأول (20)
    - التقويم الثاني (20)
    - التقويم الثالث (مشاركة وأنشطة) (20)
    - الامتحان النهائي (40)
    - المجموع الكلي (100)
    """
    if not student_names:
        student_names = [f"طالب {i+1}" for i in range(25)]

    count = len(student_names)
    df = pd.DataFrame({
        "م": range(1, count + 1),
        "اسم الطالب الرباعي": student_names,
        "التقويم الأول (20)": [18] * count,
        "التقويم الثاني (20)": [17] * count,
        "المشاركة والأنشطة (20)": [19] * count,
        "الامتحان النهائي (40)": [35] * count,
        "المجموع الكلي (100)": [89] * count,
        "التقدير": ["ممتاز"] * count
    })
    return df
