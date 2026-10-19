"""
ingest.py - إدخال وفهرسة نصوص الكتب المدرسية وكراسات الأنشطة
مع التنظيف التلقائي للأسطر الفارغة
"""

import os
import re
from typing import List, Dict

def ingest_textbook_text(raw_text: str, unit: int, page: int, subject: str) -> Dict:
    """
    تنظيف وفهرسة صفحة من كتاب المنهاج
    """
    clean = re.sub(r'\n{3,}', '\n\n', raw_text).strip()
    return {
        "unit": unit,
        "page": page,
        "subject": subject,
        "clean_content": clean,
        "char_count": len(clean)
    }
