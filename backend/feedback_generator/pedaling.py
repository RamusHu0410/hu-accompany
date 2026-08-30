"""Pedaling analysis -- not implemented yet.

Kept as its own module/function so pedal analysis can be built later
(graphical pedal-marking detection doesn't exist anywhere in the pipeline
yet -- see pdf_processor/README.md's "Known limitations") without touching
alignment.py/analysis.py/nlg.py. Not called from orchestrator.py yet, and
must not produce any pedal-related score or feedback in the meantime.
"""


def analyze_pedaling(user_data, expected_data):
    pass
