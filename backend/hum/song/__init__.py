"""The band engine: a hum's tune arranged into a song by a genre-coherent band (arranger.py), held
as one editable project (project.py) and rendered stem by stem (render.py)."""

from .arranger import ArrangeOptions, arrange, arrange_phrase
from .page_options import options_from_page
from .project import Project
from .render import Mix, export_midi, mix

__all__ = ["ArrangeOptions", "Mix", "Project", "arrange", "arrange_phrase", "export_midi", "mix", "options_from_page"]
