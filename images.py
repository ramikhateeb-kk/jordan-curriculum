"""
images.py - معالجة الصور والرسوم البيانية التوضيحية لدروس المنهاج الأردني
"""

from typing import Optional

def get_subject_illustration(subject_id: str) -> str:
    """
    إرجاع صورة دلالية لموضوع المادة
    """
    illustrations = {
        "english": "https://images.unsplash.com/photo-1456513080510-7bf3a84b82f8?w=500&q=80",
        "math": "https://images.unsplash.com/photo-1509228468518-180dd4864904?w=500&q=80",
        "science": "https://images.unsplash.com/photo-1532094349884-543bc11b234d?w=500&q=80",
        "history": "https://images.unsplash.com/photo-1461360370896-922624d12aa1?w=500&q=80",
        "geography": "https://images.unsplash.com/photo-1524661135-423995f22d0b?w=500&q=80"
    }
    return illustrations.get(subject_id, illustrations["science"])
