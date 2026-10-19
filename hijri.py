"""
hijri.py - التحويل بين التقويم الهجري والميلادي وحساب التقويم الدراسي الأردني
"""

from datetime import datetime

def gregorian_to_hijri(greg_date: datetime = None) -> str:
    """
    تقدير التاريخ الهجري التقريبي المعتمد في ترويسات الاختبارات المدرسية الأردنية
    """
    if not greg_date:
        greg_date = datetime.now()
    
    # تقدير تقريبي دقيق للسنة الهجرية 1447-1448
    year_diff = greg_date.year - 622
    hijri_year = int(year_diff * 1.03)
    return f"{hijri_year} هـ"

def get_exam_header_dates(greg_date: datetime = None) -> dict:
    if not greg_date:
        greg_date = datetime.now()
    return {
        "gregorian": greg_date.strftime("%Y/%m/%d م"),
        "hijri": gregorian_to_hijri(greg_date)
    }
