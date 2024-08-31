import typing as t
import abc
import yaml
from pathlib import Path

class Project:
    def __init__(self, path: Path):
        self.path = path


class ProjectInfo:
    def __init__(
        self,
        message: str,
        file: t.Optional[Path] = None,
        position: t.Optional[str | t.Tuple[int, int]] = None,
    ):
        self.message = message
        self.file = file
        self.position = position


class ProjectError(ProjectInfo): ...


class ProjectWarning(ProjectInfo): ...


class GithubWorkflow:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> t.Dict:
        with self.path.open() as f:
            return yaml.safe_load(f)


class Rule(abc.ABC):
    @abc.abstractmethod
    def active(self, project: Project) -> bool: ...

    @abc.abstractmethod
    def check(self, project: Project) -> t.List[ProjectInfo]: ...

    def github_workflows(self, project: Project) -> t.List[GithubWorkflow]:
        if not (project.path / ".github" / "workflows").exists():
            return []
        return list(
            GithubWorkflow(p)
            for p in (project.path / ".github" / "workflows").iterdir()
            if p.is_file() and p.name.endswith(".yml")
        )


