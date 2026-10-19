# -*- coding: utf-8 -*-
import json
import os
from typing import Dict, Any, List

CATALOG_PATH = os.path.join(os.path.dirname(__file__), "data", "catalog.json")

def load_catalog() -> Dict[str, Any]:
    if os.path.exists(CATALOG_PATH):
        with open(CATALOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"grades": []}

def get_subjects_for_grade(grade_name: str) -> List[str]:
    cat = load_catalog()
    for g in cat.get("grades", []):
        if g.get("name") == grade_name:
            return [s.get("name") for s in g.get("subjects", [])]
    return [
        "اللغة الإنجليزية (Action Pack)",
        "الرياضيات",
        "اللغة العربية (مهارات الاتصال)",
        "العلوم العامة",
        "الفيزياء",
        "تاريخ الأردن",
        "التربية الإسلامية"
    ]
