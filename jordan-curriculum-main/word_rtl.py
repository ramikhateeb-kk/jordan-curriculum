# -*- coding: utf-8 -*-
"""word_rtl.py - أدوات ضبط اتجاه النصوص العربية والإنجليزية وملفات Word"""

def set_cell_direction(cell, is_english: bool = False):
    """ضبط اتجاه الخلية LTR للإنجليزية أو RTL للعربية"""
    direction = "ltr" if is_english else "rtl"
    align = "left" if is_english else "right"
    return {"direction": direction, "align": align}

def format_bilingual_paragraph(ar_text: str, en_text: str) -> str:
    """تنسيق فقرة ثنائية اللغة بدون تداخل علامات الترقيم"""
    return f"{ar_text.strip()}\n{en_text.strip()}"
