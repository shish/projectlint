import json
import typing as t
from pathlib import Path

from ..common import FileRule, ProjectInfo, ProjectWarning, Versions


class NodeVersions(Versions):
    DEPRECATED = ["12", "14", "16", "18", "20"]
    STABLE = ["22", "24"]
    UNSTABLE = ["25"]


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


class BiomeConfig(FileRule):
    RELEVANT_PATTERNS = ["biome.json"]

    def check_file(self, file: Path) -> t.Iterator[ProjectInfo]:
        expected: dict[str, t.Any] = {
            "$schema": "./node_modules/@biomejs/biome/configuration_schema.json",
        }
        if (file.parent / ".git").exists():
            expected["vcs"] = {"enabled": True, "clientKind": "git", "useIgnoreFile": True}

        data = json.load(file.open())

        for key, expected_value in expected.items():
            if key not in data or data[key] != expected_value:
                yield ProjectWarning(
                    f"Biome config '{key}' should be {expected_value}, is {data.get(key)}",
                    file=file,
                )
