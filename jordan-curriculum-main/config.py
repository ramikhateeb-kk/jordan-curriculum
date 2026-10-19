# -*- coding: utf-8 -*-
import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
APP_TITLE = "المساعد الذكي للمناهج الأردنية"
MINISTRY_NAME = "وزارة التربية والتعليم - المملكة الأردنية الهاشمية"
DEFAULT_GRADE = "الثاني الثانوي - التوجيهي"
DEFAULT_SUBJECT = "اللغة الإنجليزية (Action Pack)"
