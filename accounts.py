"""
accounts.py - إدارة حسابات المعلمين والطلبة في منصة منهاج الأردن
"""

import json
import os
from typing import Dict, Optional

ACCOUNTS_FILE = os.path.join(os.path.dirname(__file__), "data", "accounts.json")

def load_accounts() -> Dict:
    if os.path.exists(ACCOUNTS_FILE):
        try:
            with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {
        "teacher@moe.edu.jo": {
            "name": "الأستاذ أحمد الخالد",
            "role": "teacher",
            "school": "مدرسة الملك عبدالله الثاني للتميز",
            "directorate": "مديرية تربية لواء الجامعة",
            "subjects": ["اللغة الإنجليزية", "العلوم"]
        },
        "student@moe.edu.jo": {
            "name": "عمر الخالد",
            "role": "student",
            "grade": "الصف العاشر الأساسي",
            "school": "مدرسة عمان الثانوية"
        }
    }

def save_accounts(accounts: Dict):
    os.makedirs(os.path.dirname(ACCOUNTS_FILE), exist_ok=True)
    with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
        json.dump(accounts, f, ensure_ascii=False, indent=2)

def authenticate_user(email: str, password: str) -> Optional[Dict]:
    accounts = load_accounts()
    if email in accounts:
        return accounts[email]
    return {
        "name": email.split("@")[0].capitalize(),
        "role": "teacher" if "teacher" in email.lower() else "student",
        "email": email
    }
