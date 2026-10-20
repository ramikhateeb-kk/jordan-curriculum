import os
from pathlib import Path

BASE = Path(__file__).parent
PDF_DIR = BASE / "data" / "pdfs"      # data/pdfs/<grade>/<semester>/<slug>.pdf  (تُحمَّل تلقائيًا من رابط الكتاب)
INDEX_DIR = BASE / "data" / "index"   # نص الكتاب المقسّم للبحث المحلي

# غيّر اسم النموذج إن تغيّر في Google AI Studio
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

GRADES = ["الأول", "الثاني", "الثالث", "الرابع", "الخامس", "السادس",
          "السابع", "الثامن", "التاسع", "العاشر", "الحادي عشر", "الثاني عشر"]
