import json
import typing as t
from pathlib import Path

from ..common import Project, ProjectInfo, ProjectError, ProjectWarning, FileRule


class JSPackageDeps(FileRule):
    RELEVANT_PATTERNS = ["package.json"]
    EXPECTED_PACKAGES = {
        "react": "^18",
        "typescript": "^5.4",
    }

    def check_file(self, file: Path) -> t.Iterator[ProjectInfo]:
        data = json.load(file.open())

        # merge two dicts
        deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}

        for package, expected_version in self.EXPECTED_PACKAGES.items():
            if package in deps and not deps[package].startswith(expected_version):
                yield ProjectWarning(
                    f"{package} should be {expected_version}, is {deps[package]}",
                    file=file,
                )
