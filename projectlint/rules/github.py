import typing as t
import logging
import json
from pathlib import Path

from ..common import (
    GithubWorkflow,
    ProjectInfo,
    ProjectError,
    ProjectWarning,
    Rule,
    FileRule,
)
from .php import PHP_DEPRECATED, PHP_STABLE, PHP_UNSTABLE

log = logging.getLogger(__name__)


class GithubActionsOn(FileRule):
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


class GithubActionsRunsOn(FileRule):
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


class GithubActionsPHPMatrixVersions(FileRule):
    """
    When testing PHP projects, we should test against all currently-supported
    versions of PHP, and not deprecated versions.
    """

    RELEVANT_PATTERNS = [".github/workflows/*.yml"]

    def check_file(self, file: Path) -> t.Iterator[ProjectInfo]:
        wf = GithubWorkflow(file)
        data = wf.load()
        jobs = data.get("jobs", {})
        for name, job in jobs.items():
            matrix = job.get("strategy", {}).get("matrix", {})
            for key in matrix:
                if key.startswith("php"):
                    versions = matrix[key]
                    if len(versions) > 1 and any(
                        version[0] == "8" for version in versions
                    ):
                        # This looks like a PHP versions matrix, let's check it
                        for deprecated in PHP_DEPRECATED:
                            for version in versions:
                                if version.startswith(deprecated):
                                    yield ProjectError(
                                        f"PHP {version} is deprecated",
                                        file=wf.path,
                                        position=f"jobs.{name}.strategy.matrix.{key}",
                                    )
                        for stable in PHP_STABLE:
                            if stable not in versions:
                                yield ProjectError(
                                    f"PHP {stable} is not tested",
                                    file=wf.path,
                                    position=f"jobs.{name}.strategy.matrix.{key}",
                                )
                        for unstable in PHP_UNSTABLE:
                            if unstable not in versions:
                                yield ProjectInfo(
                                    f"PHP {unstable} is not tested",
                                    file=wf.path,
                                    position=f"jobs.{name}.strategy.matrix.{key}",
                                )


class GithubActionsActionVersions(FileRule):
    RELEVANT_PATTERNS = [".github/workflows/*.yml"]

    def check_file(self, file: Path) -> t.Iterator[ProjectInfo]:
        ACTION_VERSIONS = {
            "actions/checkout": "v4",
            "actions/cache": "v4",
            "php-actions/composer": "v6",
            "shivammathur/setup-php": "v2",
            "actions/setup-python": "v5",
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
                        if version != ACTION_VERSIONS[action]:
                            yield ProjectError(
                                f"{action} should be {ACTION_VERSIONS[action]}, is {version}",
                                file=wf.path,
                                position=f"jobs.{job_name}.steps[{step_n}].uses",
                            )


class GithubActionsVendoredPHPTools(Rule):
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
            "phpunit/phpunit": ["vendor/bin/phpunit", "composer test"],
            "phpstan/phpstan": ["vendor/bin/phpunit", "composer stan"],
            "friendsofphp/php-cs-fixer": ["vendor/bin/phpunit", "composer format"],
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
                    f"{binary} is vendored but not used in a workflow",
                    file=None,
                    position=f"require-dev.{tool}",
                )
