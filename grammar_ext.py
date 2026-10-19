"""
grammar_ext.py - استخراج وتلخيص قواعد اللغة الإنجليزية والعربية في المنهاج الأردني
مع ضمان التنسيق السليم LTR لقواعد Action Pack
"""

ACTION_PACK_GRAMMAR = {
    "present_simple": {
        "title": "Present Simple Tense",
        "form": "Subject + Verb (s/es with he/she/it)",
        "uses": ["Habits and daily routines", "General facts and scientific truths", "Timetables"],
        "keywords": ["always", "usually", "often", "sometimes", "never", "every day"],
        "examples": [
            "We study English at school every week.",
            "Water boils at 100 degrees Celsius."
        ]
    },
    "past_simple": {
        "title": "Past Simple Tense",
        "form": "Subject + Verb 2 (regular: -ed / irregular list)",
        "uses": ["Completed actions at a specific time in the past"],
        "keywords": ["yesterday", "last week", "ago", "in 2020"],
        "examples": [
            "Ali traveled to Petra last summer.",
            "They saw the Roman ruins in Jerash."
        ]
    },
    "present_perfect": {
        "title": "Present Perfect Tense",
        "form": "Subject + have/has + Past Participle (V3)",
        "uses": ["Experiences without stating exact time", "Actions completed recently with present effect"],
        "keywords": ["already", "yet", "just", "since", "for", "ever", "never"],
        "examples": [
            "I have already finished my homework.",
            "She has lived in Amman since 2015."
        ]
    }
}

def get_grammar_rule(rule_key: str):
    return ACTION_PACK_GRAMMAR.get(rule_key, ACTION_PACK_GRAMMAR["present_simple"])
