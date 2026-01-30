"""
Load and format system prompts from the prompts/ folder.
Use .format() placeholders in .txt files; pass kwargs when formatting.
"""
from pathlib import Path
import re

PROMPTS_DIR = Path(__file__).resolve().parent


def load(name: str) -> str:
    """Load a prompt template by name (without .txt). E.g. load('main_agent_system')."""
    path = PROMPTS_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt not found: {path}")
    return path.read_text(encoding="utf-8").rstrip()


def format_prompt(template: str, **kwargs: str) -> str:
    """
    Format template with kwargs. Uses str.format().
    Any {key} in template must be in kwargs; missing keys are replaced with ''.
    """
    # Ensure all placeholders have a value (default '')
    placeholders = re.findall(r"\{(\w+)\}", template)
    for k in placeholders:
        if k not in kwargs:
            kwargs[k] = ""
    return template.format(**kwargs)
