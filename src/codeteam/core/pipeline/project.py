from dataclasses import dataclass


@dataclass(frozen = True)
class ProjectSettings:
    path: str
    task: str