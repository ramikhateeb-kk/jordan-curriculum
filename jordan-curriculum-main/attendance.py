# -*- coding: utf-8 -*-
"""attendance.py - سجل دوام وغياب الطلبة المدرسي"""

def record_attendance(date_str: str, student_id: str, status: str = "حاضر"):
    return {"date": date_str, "student_id": student_id, "status": status}
