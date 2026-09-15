"""Load versioned internal instructions distributed with the package."""

from importlib.resources import files


def load_prompt(name: str) -> str:
    return (files("cfd_agent.prompts") / f"{name}.md").read_text(encoding="utf-8")
