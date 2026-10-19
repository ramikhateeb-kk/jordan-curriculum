"""
word_rtl.py - معالجة اتجاه النصوص والتصدير لملفات Word / PDF
مع الفصل التام بين اتجاه اللغة الإنجليزية LTR واللغة العربية RTL
"""

def wrap_text_direction(text: str, is_english: bool = False) -> str:
    """
    تغليف النص باتجاه صحيح بحيث لا تنقلب الجمل الإنجليزية
    """
    if is_english:
        return f"\u202A{text}\u202C"  # LTR embedding
    return f"\u202B{text}\u202C"  # RTL embedding

def clean_arabic_english_mix(text: str) -> str:
    # يمنع اختلاط علامات الترقيم الإنجليزية بالنصوص العربية
    return text.replace("?", "؟") if not any(c in text for c in "abcdefghijklmnopqrstuvwxyz") else text
