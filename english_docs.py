"""
english_docs.py - أدوات تنسيق ومعالجة وثائق ومناهج اللغة الإنجليزية
يضمن عرض الشرح بتنسيق LTR صحيح دون قلب الكلمات أو تشويه علامات الترقيم
"""

import re

def format_english_explanation_html(text: str) -> str:
    """
    تنسيق نصوص الشرح الإنجليزية داخل حاوية LTR واضحة مع خط لاتيني مناسب
    """
    clean = re.sub(r'\n{3,}', '\n\n', text).strip()
    
    html = f"""
    <div dir="ltr" style="
        text-align: left;
        font-family: 'Inter', system-ui, -apple-system, sans-serif;
        line-height: 1.7;
        direction: ltr;
        background-color: #f8fafc;
        border-radius: 12px;
        padding: 16px 20px;
        border: 1px solid #e2e8f0;
        color: #1e293b;
        margin: 10px 0;
    ">
        <div style="white-space: pre-line; font-size: 15px;">
            {clean}
        </div>
    </div>
    """
    return html

def is_english_content(text: str) -> bool:
    """
    فحص ما إذا كان النص يحتوي على نسبة غالبة من الأحرف الإنجليزية
    """
    if not text:
        return False
    english_chars = len(re.findall(r'[a-zA-Z]', text))
    arabic_chars = len(re.findall(r'[\u0600-\u06FF]', text))
    return english_chars > arabic_chars
