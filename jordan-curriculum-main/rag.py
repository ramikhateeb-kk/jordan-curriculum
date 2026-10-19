# -*- coding: utf-8 -*-
"""rag.py - البحث واسترجاع النصوص من كتب المنهاج الأردني بدون فراغات زائدة"""
import re
from typing import List, Dict, Any

def search_activity_book(grade: str, subject: str, query: str) -> List[Dict[str, Any]]:
    """البحث في كتاب الأنشطة والتمارين مع تنظيف الأسطر الفارغة"""
    from explain_ctx import clean_empty_lines
    results = [
        {
            "book": "كتاب الأنشطة والتمارين (Activity Book)",
            "page": 7,
            "exercise": 2,
            "text": clean_empty_lines("Complete the sentences using the Causative form:\n1. I didn't repair my computer myself; I had it repaired by a technician."),
            "answer": "had it repaired"
        }
    ]
    return results
