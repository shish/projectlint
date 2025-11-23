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
        "prettier": "^3.6",
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


class PrettierConfig(FileRule):
    RELEVANT_PATTERNS = ["package.json"]
    EXPECTED_CONFIG = {
        # "tabWidth": 4,
        "trailingComma": "all",
        "plugins": ["prettier-plugin-organize-imports"],
    }

    def check_file(self, file: Path) -> t.Iterator[ProjectInfo]:
        data = json.load(file.open())
        if "prettier" not in data.get("devDependencies", {}):
            return

        data = data.get("prettier", {})
        for key, expected_value in self.EXPECTED_CONFIG.items():
            if key not in data or data[key] != expected_value:
                yield ProjectWarning(
                    f"Prettier config '{key}' should be {expected_value}, is {data.get(key)}",
                    file=file,
                )
