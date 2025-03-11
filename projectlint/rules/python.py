import typing as t
from pathlib import Path

from ..common import ProjectInfo, ProjectWarning, FileRule, Versions


class PythonVersions(Versions):
    # FIXME: we skip 3.1 because it gives false-positives that 3.10 is deprecated
    DEPRECATED = ["2", "3.0", "3.2", "3.3", "3.4", "3.5", "3.6", "3.7", "3.8"]
    STABLE = ["3.9", "3.10", "3.11", "3.12"]
    UNSTABLE = ["3.13"]


class SetupPy(FileRule):
    RELEVANT_PATTERNS = ["setup.py"]

    def check_file(self, file: Path) -> t.Iterator[ProjectInfo]:
        yield ProjectWarning("setup.py is deprecated, use pyproject.toml", file=file)
