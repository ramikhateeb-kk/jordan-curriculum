# -*- coding: utf-8 -*-
"""quiz.py"""
def create_quiz(subject: str, count: int = 5):
    return [{"id": i, "question": f"Question {i}"} for i in range(1, count + 1)]
