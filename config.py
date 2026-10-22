import os
from pathlib import Path

BASE = Path(__file__).parent
PDF_DIR = BASE / "data" / "pdfs"      # data/pdfs/<grade>/<semester>/<slug>.pdf  (تُحمَّل تلقائيًا من رابط الكتاب)
INDEX_DIR = BASE / "data" / "index"   # نص الكتاب المقسّم للبحث المحلي

# نموذج افتراضي حديث. إذا بقي اسم نموذج قديم في Secrets/Environment، نتجاوزه تلقائيًا.
_configured_model = os.getenv("GEMINI_MODEL", "").strip()
_retired_models = {"gemini-2.0-flash", "models/gemini-2.0-flash"}
GEMINI_MODEL = "gemini-3.8-flash" if _configured_model.lower() in _retired_models else (_configured_model or "gemini-3.8-flash")

GRADES = ["الأول", "الثاني", "الثالث", "الرابع", "الخامس", "السادس",
          "السابع", "الثامن", "التاسع", "العاشر", "الحادي عشر", "الثاني عشر"]
