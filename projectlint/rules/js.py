import json
import typing as t
from pathlib import Path

from ..common import ProjectInfo, ProjectWarning, FileRule, Versions


class NodeVersions(Versions):
    DEPRECATED = ["12", "14", "16", "18", "20"]
    STABLE = ["22"]
    UNSTABLE = ["24"]


class JSPackageDeps(FileRule):
    RELEVANT_PATTERNS = ["package.json"]
    EXPECTED_PACKAGES = {
        "react": "^19",
        "typescript": "^5.9",
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
