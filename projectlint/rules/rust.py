import tomllib
import typing as t
from pathlib import Path

from ..common import FileRule, ProjectInfo, ProjectWarning, Versions


class CargoEdition(FileRule):
    RELEVANT_PATTERNS = ["Cargo.toml"]

    def check_file(self, file: Path) -> t.Iterator[ProjectInfo]:
        data = tomllib.load(file.open("rb"))

        ed = data.get("package", {}).get("edition")
        if ed not in ["2021", "2024"]:
            yield ProjectWarning(
                f"Cargo edition should be 2021/2024, is {ed}",
                file=file,
                position="package.edition",
            )


class ClippyRules(FileRule):
    RELEVANT_PATTERNS = ["Cargo.toml"]

    def check_file(self, file: Path) -> t.Iterator[ProjectInfo]:
        data = tomllib.load(file.open("rb"))
        lints = data.get("lints", {}).get("clippy", {})
        expected_rules = {
            "dbg_macro": "deny",
            "unwrap_used": "deny",
            "expect_used": "deny",
        }

        for rule, expected_value in expected_rules.items():
            actual_value = lints.get(rule)
            if actual_value != expected_value:
                yield ProjectWarning(
                    f"Clippy rule '{rule}' should be '{expected_value}', is '{actual_value}'",
                    file=file,
                    position=f"lints.clippy.{rule}",
                )
