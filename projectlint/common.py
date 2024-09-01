import typing as t
import abc
import yaml
from pathlib import Path
import logging

log = logging.getLogger(__name__)


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
    IGNORE_PATHS = [
        "node_modules",
        "vendor",
        "target",
        "venv",
        "__pycache__",
        ".git",
        ".hg",
        ".sl",
    ]
    RELEVANT_PATTERNS = []

    def __init__(self, project: Project):
        self.project = project
        self.relevant_paths = []
        for pattern in self.RELEVANT_PATTERNS:
            for file in self.find_files(pattern):
                self.relevant_paths.append(file)

    def active(self) -> bool:
        return bool(self.relevant_paths)

    @abc.abstractmethod
    def check(self) -> t.Iterator[ProjectInfo]:
        ...

    def find_files(self, pattern: str) -> t.Iterator[Path]:
        return [
            p
            for p in self.project.path.rglob(pattern)
            if not any(p.parts[i] in self.IGNORE_PATHS for i in range(len(p.parts)))
        ]

class FileRule(Rule):
    def check(self) -> t.Iterator[ProjectInfo]:
        for path in self.relevant_paths:
            log.debug(f"...check_file({path})")
            yield from self.check_file(path)

    @abc.abstractmethod
    def check_file(self, path: Path) -> t.Iterator[ProjectInfo]: ...
