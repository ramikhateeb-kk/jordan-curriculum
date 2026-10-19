"""
plan_cache.py - التخزين المؤقت للخطط والشروحات لسرعة الاستجابة
"""

import time
from typing import Optional, Dict

_CACHE: Dict[str, Dict] = {}
CACHE_TTL = 3600  # 1 hour

def get_cached_plan(key: str) -> Optional[str]:
    entry = _CACHE.get(key)
    if entry and (time.time() - entry["timestamp"] < CACHE_TTL):
        return entry["data"]
    return None

def set_cached_plan(key: str, data: str):
    _CACHE[key] = {
        "data": data,
        "timestamp": time.time()
    }
