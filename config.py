import os
from dotenv import load_dotenv

load_dotenv()

# Gemini AI API Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Default Jordan Ministry of Education Settings
DEFAULT_GRADE = "الصف الرابع الأساسي"
DEFAULT_SEMESTER = "الفصل الأول"
APP_NAME = "رفيق المنهاج الأردني المطور - المعلم الذكي"

# Model Configuration
DEFAULT_MODEL = "gemini-3.8-flash"
