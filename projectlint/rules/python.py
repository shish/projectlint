import typing as t
import tomllib
from pathlib import Path

from ..common import ProjectInfo, ProjectWarning, FileRule, Versions


class PythonVersions(Versions):
    # FIXME: we skip 3.1 because it gives false-positives that 3.1X is deprecated
    DEPRECATED = [
        "2",
        "3.0",
        "3.2",
        "3.3",
        "3.4",
        "3.5",
        "3.6",
        "3.7",
        "3.8",
        "3.9",
        "3.10",
        "3.11",
        "3.12",
    ]
    STABLE = ["3.13", "3.14"]
    UNSTABLE = ["3.15"]


class SetupPy(FileRule):
    RELEVANT_PATTERNS = ["setup.py"]

    def check_file(self, file: Path) -> t.Iterator[ProjectInfo]:
        yield ProjectWarning("setup.py is deprecated, use pyproject.toml", file=file)


class PyProject(FileRule):
    RELEVANT_PATTERNS = ["pyproject.toml"]

    def check_file(self, file: Path) -> t.Iterator[ProjectInfo]:
        data = tomllib.load(file.open("rb"))
        reqpy = data.get("project", {}).get("requires-python")
        okreqs = [f">={v}" for v in PythonVersions.STABLE]
        if not any(reqpy.startswith(f">={v}") for v in PythonVersions.STABLE):
            yield ProjectWarning(
                f"requires-python: {reqpy} should be one of {okreqs}",
                file=file,
                position="project.requires-python",
            )

        if "test" in data.get("project", {}).get("optional-dependencies", {}):
            yield ProjectWarning(
                "project.optional-dependencies.dev is deprecated, use dependency-groups instead",
                file=file,
                position="project.optional-dependencies.dev",
            )

        # check that dependency-groups.dev contains pytest, black, and mypy
        dev_deps = data.get("dependency-groups", {}).get("dev", [])
        expected_deps = [
            ["pytest"],
            ["ruff"],
            ["mypy", "ty"],
        ]
        for tool_choices in expected_deps:
            if not any(
                any(d.startswith(dep) for d in dev_deps) for dep in tool_choices
            ):
                yield ProjectWarning(
                    f"dependency-groups.dev should contain one of {tool_choices}",
                    file=file,
                    position="dependency-groups.dev",
                )


class PythonVersion(FileRule):
    RELEVANT_PATTERNS = [".python-version"]

    def check_file(self, file: Path) -> t.Iterator[ProjectInfo]:
        first_line = file.open().readline().strip()
        if first_line not in PythonVersions.STABLE + PythonVersions.UNSTABLE:
            yield ProjectWarning(
                f".python-version: {first_line} should be one of {PythonVersions.STABLE + PythonVersions.UNSTABLE}",
                file=file,
            )
