# -*- coding: utf-8 -*-
"""english_docs.py & grammar_ext.py - مستندات وقواعد منهاج Action Pack الأردني"""

ACTION_PACK_GRAMMAR = {
    "Grade 12": ["Tenses Revision", "Reported Speech", "Passive Voice", "Causative Verbs", "Used to vs Be used to"],
    "Grade 10": ["Present Simple & Continuous", "Stative Verbs", "Past Simple & Continuous", "Passive Voice"],
    "Grade 7": ["Present Simple & Continuous", "Personality Adjectives", "Past Continuous with while/when"],
    "Grade 4": ["Going to (Future)", "Must / Mustn't", "Past Simple Regular Verbs"]
}

def get_grammar_summary(grade: str) -> list:
    return ACTION_PACK_GRAMMAR.get(grade, ["General Action Pack Grammar Rules"])
