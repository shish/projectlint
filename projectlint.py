#!/usr/bin/env python3

import abc
import argparse
import sys
import typing as t
from pathlib import Path
import yaml
import logging
import json

log = logging.getLogger(__name__)

# https://www.php.net/supported-versions.php
PHP_DEPRECATED = ["7", "8.0", "8.1"]
PHP_STABLE = ["8.2", "8.3"]
PHP_UNSTABLE = ["8.4"]


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
    @abc.abstractmethod
    def active(self, project: Project) -> bool: ...

    @abc.abstractmethod
    def check(self, project: Project) -> t.List[ProjectInfo]: ...

    def github_workflows(self, project: Project) -> t.List[GithubWorkflow]:
        if not (project.path / ".github" / "workflows").exists():
            return []
        return list(
            GithubWorkflow(p)
            for p in (project.path / ".github" / "workflows").iterdir()
            if p.is_file() and p.name.endswith(".yml")
        )


class PHPComposerDeps(Rule):
    def active(self, project: Project) -> bool:
        return (project.path / "composer.json").exists()

    def check(self, project: Project) -> t.List[ProjectInfo]:
        file = project.path / "composer.json"
        with file.open() as f:
            data = json.load(f)
        infos: t.List[ProjectInfo] = []

        # we should support "oldest supported PHP version" and newer
        if "require" not in data:
            infos.append(
                ProjectWarning(
                    "No dependencies are required, should at least require php",
                    file=file,
                )
            )
        elif "php" not in data["require"]:
            infos.append(
                ProjectWarning("PHP should be required", file=file, position="require")
            )
        else:
            php_version = data["require"]["php"]
            if php_version != f"^{PHP_STABLE[0]}":
                infos.append(
                    ProjectWarning(
                        f"should be ^{PHP_STABLE[0]}, is {php_version}",
                        file=file,
                        position="require.php",
                    )
                )

        # dev tools should be current
        if "require-dev" not in data:
            infos.append(
                ProjectWarning(
                    "No dev dependencies are required, should at least require phpunit",
                    file=file,
                )
            )
        else:
            for tool, stable in {
                "phpunit/phpunit": "^11.0",
                "phpstan/phpstan": "^1.12",
                "friendsofphp/php-cs-fixer": "^3.64",
            }.items():
                if tool not in data["require-dev"]:
                    infos.append(
                        ProjectWarning(
                            f"{tool} should be required",
                            file=file,
                            position="require-dev",
                        )
                    )
                else:
                    version = data["require-dev"][tool]
                    if version != stable:
                        infos.append(
                            ProjectWarning(
                                f"should be {stable}, is {version}",
                                file=file,
                                position=f"require-dev.{tool}",
                            )
                        )

        return infos


class PHPComposerLock(Rule):
    def active(self, project: Project) -> bool:
        return (project.path / "composer.lock").exists()

    def check(self, project: Project) -> t.List[ProjectInfo]:
        # check that composer.lock is up to date with composer.json
        infos: t.List[ProjectInfo] = []
        json_modified = (project.path / "composer.json").stat().st_mtime
        lock_modified = (project.path / "composer.lock").stat().st_mtime
        if json_modified > lock_modified:
            infos.append(
                ProjectError(
                    "composer.lock is out of date", file=project.path / "composer.lock"
                )
            )
        return infos


class GithubActionsOn(Rule):
    def active(self, project: Project) -> bool:
        return len(self.github_workflows(project)) != 0

    def check(self, project: Project) -> t.List[ProjectInfo]:
        infos: t.List[ProjectInfo] = []
        for wf in self.github_workflows(project):
            logging.debug(f"Checking {wf.path}")
            data = wf.load()
            on = data.get(True)  # yaml treats 'on' as a boolean...
            if not on:
                continue
            if isinstance(on, str):
                log.debug("on is a string, converting to dict")
                on = {x.strip(): {} for x in on.split(",")}
            if isinstance(on, list):
                log.debug("on is a list, converting to dict")
                on = {x.strip(): {} for x in on}
            log.debug(f"on: {on}")
            if "push" in on and "pull_request" in on:
                if (not on["push"]) or ("branches" not in on["push"]):
                    infos.append(
                        ProjectError(
                            "If an action is triggered by both push and pull_request, it should have a 'branches' filter to avoid running twice",
                            file=wf.path,
                        )
                    )
        return infos


class GithubActionsRunsOn(Rule):
    def active(self, project: Project) -> bool:
        return len(self.github_workflows(project)) != 0

    def check(self, project: Project) -> t.List[ProjectInfo]:
        infos: t.List[ProjectInfo] = []
        for wf in self.github_workflows(project):
            logging.debug(f"Checking {wf.path}")
            data = wf.load()
            jobs = data.get("jobs", {})
            for name, job in jobs.items():
                runs_on = job.get("runs-on")
                if runs_on == "ubuntu-latest":
                    infos.append(
                        ProjectWarning(
                            "ubuntu-latest is not recommended, use ubuntu-24.04",
                            file=wf.path,
                            position=f"jobs.{name}.runs-on",
                        )
                    )
        return infos


class GithubActionsPHPVersions(Rule):
    """
    When testing PHP projects, we should test against all currently-supported
    versions of PHP, and not deprecated versions.
    """

    def active(self, project: Project) -> bool:
        return len(self.github_workflows(project)) != 0

    def check(self, project: Project) -> t.List[ProjectInfo]:
        infos: t.List[ProjectInfo] = []
        for wf in self.github_workflows(project):
            logging.debug(f"Checking {wf.path}")
            data = wf.load()
            jobs = data.get("jobs", {})
            for name, job in jobs.items():
                matrix = job.get("strategy", {}).get("matrix", {})
                for key in matrix:
                    if key.startswith("php"):
                        versions = matrix[key]
                        if any(version[0] == "8" for version in versions):
                            # This looks like a PHP versions matrix, let's check it
                            for deprecated in PHP_DEPRECATED:
                                for version in versions:
                                    if version.startswith(deprecated):
                                        infos.append(
                                            ProjectError(
                                                f"PHP {version} is deprecated",
                                                file=wf.path,
                                                position=f"jobs.{name}.strategy.matrix.{key}",
                                            )
                                        )
                            for stable in PHP_STABLE:
                                if stable not in versions:
                                    infos.append(
                                        ProjectError(
                                            f"PHP {stable} is not tested",
                                            file=wf.path,
                                            position=f"jobs.{name}.strategy.matrix.{key}",
                                        )
                                    )
                            for unstable in PHP_UNSTABLE:
                                if unstable not in versions:
                                    infos.append(
                                        ProjectInfo(
                                            f"PHP {unstable} is not tested",
                                            file=wf.path,
                                            position=f"jobs.{name}.strategy.matrix.{key}",
                                        )
                                    )
        return infos


class GithubActionsActionVersions(Rule):
    def active(self, project: Project) -> bool:
        return len(self.github_workflows(project)) != 0

    def check(self, project: Project) -> t.List[ProjectInfo]:
        ACTION_VERSIONS = {
            "actions/checkout": "v4",
            "actions/cache": "v4",
            "php-actions/composer": "v6",
            "shivammathur/setup-php": "v2",
        }
        infos: t.List[ProjectInfo] = []
        for wf in self.github_workflows(project):
            logging.debug(f"Checking {wf.path}")
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
                                infos.append(
                                    ProjectError(
                                        f"{action} should be {ACTION_VERSIONS[action]}, is {version}",
                                        file=wf.path,
                                        position=f"jobs.{job_name}.steps[{step_n}].uses",
                                    )
                                )
        return infos


class GithubActionsVendoredPHPTools(Rule):
    def active(self, project: Project) -> bool:
        return (len(self.github_workflows(project)) != 0) and (
            project.path / "composer.json"
        ).exists()

    def check(self, project: Project) -> t.List[ProjectInfo]:
        composer_data = json.load((project.path / "composer.json").open())
        vendored_tools = composer_data.get("require-dev", {}).keys()

        infos: t.List[ProjectInfo] = []
        for tool in vendored_tools:
            logging.debug(f"Checking that {tool} is used in a workflow")
            binary = tool.split("/")[-1]

            tool_used = False
            for wf in self.github_workflows(project):
                data = wf.load()
                for job_name, job in data.get("jobs", {}).items():
                    for step_n, step in enumerate(job.get("steps", [])):
                        if "run" in step:
                            if binary in step["run"]:
                                tool_used = True
                                break
            if not tool_used:
                infos.append(
                    ProjectWarning(
                        f"{binary} is vendored but not used in a workflow",
                        file=project.path / "composer.json",
                        position=f"require-dev.{tool}",
                    )
                )
        return infos


def main(argv: t.Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description="Lint a project")
    parser.add_argument(
        "project", help="The project to lint", type=Path, default=Path.cwd()
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show verbose output"
    )
    args = parser.parse_args(argv[1:])

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    log.info(f"Linting project {args.project}")

    rule_subclasses: t.List[t.Type[Rule]] = Rule.__subclasses__()
    rules: t.List[Rule] = [r() for r in rule_subclasses]
    fail = False

    project = Project(args.project)
    for rule in rules:
        if not rule.active(project):
            log.debug(f"Skipping {rule.__class__.__name__}")
            continue
        log.debug(f"Checking {rule.__class__.__name__}")
        infos = rule.check(project)
        for info in infos:
            if isinstance(info, ProjectError):
                print(f"Error: {info.file}:{info.position}: {info.message}")
                fail = True
            elif isinstance(info, ProjectWarning):
                print(f"Warning: {info.file}:{info.position}: {info.message}")
            else:
                print(f"Info: {info.file}:{info.position}: {info.message}")

    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
