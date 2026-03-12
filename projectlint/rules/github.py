import typing as t
import logging
import json
import abc
from pathlib import Path

from ..common import (
    GithubWorkflow,
    ProjectInfo,
    ProjectError,
    ProjectWarning,
    Rule,
    FileRule,
    Versions,
)
from . import php
from . import python
from . import js

log = logging.getLogger(__name__)


class On(FileRule):
    RELEVANT_PATTERNS = [".github/workflows/*.yml"]

    def check_file(self, file: Path) -> t.Iterator[ProjectInfo]:
        wf = GithubWorkflow(file)
        data = wf.load()
        on = data.get(True)  # yaml treats 'on' as a boolean...
        if not on:
            return
        if isinstance(on, str):
            log.debug("on is a string, converting to dict")
            on = {x.strip(): {} for x in on.split(",")}
        if isinstance(on, list):
            log.debug("on is a list, converting to dict")
            on = {x.strip(): {} for x in on}
        log.debug(f"on: {on}")
        if "push" in on and "pull_request" in on:
            if (not on["push"]) or ("branches" not in on["push"]):
                yield ProjectError(
                    "If an action is triggered by both push and pull_request, it should have a 'branches' filter to avoid running twice",
                    file=wf.path,
                )


class RunsOn(FileRule):
    RELEVANT_PATTERNS = [".github/workflows/*.yml"]

    def check_file(self, file: Path) -> t.Iterator[ProjectInfo]:
        wf = GithubWorkflow(file)
        data = wf.load()
        jobs = data.get("jobs", {})
        for name, job in jobs.items():
            runs_on = job.get("runs-on")
            if runs_on == "ubuntu-latest":
                yield ProjectWarning(
                    "ubuntu-latest is not recommended, use ubuntu-24.04",
                    file=wf.path,
                    position=f"jobs.{name}.runs-on",
                )


class BaseVersionsMatrix(FileRule):
    """
    When an action runs on a matrix of versions, we should test against
    all currently-supported versions, and not deprecated ones.
    """

    RELEVANT_PATTERNS = [".github/workflows/*.yml"]

    @property
    @abc.abstractmethod
    def VERSIONS(cls) -> Versions: ...

    def check_file(self, file: Path) -> t.Iterator[ProjectInfo]:
        wf = GithubWorkflow(file)
        data = wf.load()
        jobs = data.get("jobs", {})
        for name, job in jobs.items():
            matrix = job.get("strategy", {}).get("matrix", {})
            for key in matrix:
                if key.startswith(self.NAME.lower()):
                    versions = matrix[key]
                    for deprecated in self.VERSIONS.DEPRECATED:
                        for version in versions:
                            if version.startswith(deprecated):
                                yield ProjectError(
                                    f"{self.NAME} {version} is deprecated",
                                    file=wf.path,
                                    position=f"jobs.{name}.strategy.matrix.{key}",
                                )
                    for stable in self.VERSIONS.STABLE:
                        if stable not in versions:
                            yield ProjectError(
                                f"{self.NAME} {stable} is not tested",
                                file=wf.path,
                                position=f"jobs.{name}.strategy.matrix.{key}",
                            )
                    for unstable in self.VERSIONS.UNSTABLE:
                        if unstable not in versions:
                            yield ProjectInfo(
                                f"{self.NAME} {unstable} is not tested",
                                file=wf.path,
                                position=f"jobs.{name}.strategy.matrix.{key}",
                            )


class PHPVersionsMatrix(BaseVersionsMatrix):
    NAME = "PHP"
    VERSIONS = php.PHPVersions


class PythonVersionsMatrix(BaseVersionsMatrix):
    NAME = "Python"
    VERSIONS = python.PythonVersions


class NodeVersionsMatrix(BaseVersionsMatrix):
    NAME = "Node"
    VERSIONS = js.NodeVersions


class PythonVersionSetup(FileRule):
    VERSIONS = python.PythonVersions
    RELEVANT_PATTERNS = [".github/workflows/*.yml"]

    def check_file(self, file: Path) -> t.Iterator[ProjectInfo]:
        wf = GithubWorkflow(file)
        data = wf.load()
        jobs = data.get("jobs", {})
        for name, job in jobs.items():
            steps = job.get("steps", {})
            for n, step in enumerate(steps):
                if step.get("uses", "").startswith("actions/setup-python"):
                    version = step.get("with", {}).get("python-version")
                    if version is None or "$" in version or ".x" in version:
                        continue
                    if version not in self.VERSIONS.STABLE:
                        yield ProjectError(
                            f"Python {version} is not stable",
                            file=wf.path,
                            position=f"jobs.{name}.steps[{n}].with.python-version",
                        )


class ActionVersions(FileRule):
    RELEVANT_PATTERNS = [".github/workflows/*.yml"]

    def check_file(self, file: Path) -> t.Iterator[ProjectInfo]:
        ACTION_VERSIONS = {
            "actions/checkout": "v6",
            "actions/cache": "v5",
            "php-actions/composer": None,  # use default composer or setup-php instead
            "shivammathur/setup-php": "v2",
            "actions/setup-python": "v6",
        }
        wf = GithubWorkflow(file)
        data = wf.load()
        jobs = data.get("jobs", {})
        for job_name, job in jobs.items():
            for step_n, step in enumerate(job.get("steps", [])):
                if "uses" in step:
                    if "@" in step["uses"]:
                        action, version = step["uses"].split("@")
                    else:
                        action = step["uses"]
                        version = None
                    if action in ACTION_VERSIONS:
                        if ACTION_VERSIONS[action] is None:
                            yield ProjectWarning(
                                f"{action} should not be used",
                                file=wf.path,
                                position=f"jobs.{job_name}.steps[{step_n}].uses",
                            )
                        elif version != ACTION_VERSIONS[action]:
                            yield ProjectError(
                                f"{action} should be {ACTION_VERSIONS[action]}, is {version}",
                                file=wf.path,
                                position=f"jobs.{job_name}.steps[{step_n}].uses",
                            )


class VendoredPHPTools(Rule):
    def active(self) -> bool:
        wfs = self.find_files(".github/workflows/*.yml")
        comps = self.find_files("composer.json")
        return len(wfs) != 0 and len(comps) != 0

    def check(self) -> t.Iterator[ProjectInfo]:
        wfs = [GithubWorkflow(w) for w in self.find_files(".github/workflows/*.yml")]
        comps = self.find_files("composer.json")

        dev_deps = []
        for comp in comps:
            composer_data = json.load(comp.open())
            dev_deps.extend(composer_data.get("require-dev", {}).keys())

        known_tools = {
            "phpunit/phpunit": ["composer test"],
            "phpstan/phpstan": ["composer analyse-ci"],
            "friendsofphp/php-cs-fixer": ["composer format"],
        }

        for dep in dev_deps:
            if dep not in known_tools:
                continue
            tool = dep
            binaries = known_tools[dep]
            log.debug(f"Checking that {dep} is used in a workflow")

            tool_used = False
            for wf in wfs:
                data = wf.load()
                for job_name, job in data.get("jobs", {}).items():
                    for step_n, step in enumerate(job.get("steps", [])):
                        if "run" in step:
                            for binary in binaries:
                                if binary in step["run"]:
                                    tool_used = True
                                    break
            if not tool_used:
                yield ProjectWarning(
                    f"{binaries[0]} is vendored but not used in a workflow",
                    file=None,
                    position=f"require-dev.{tool}",
                )
