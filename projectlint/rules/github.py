import typing as t
import logging
import json

from ..common import Project, ProjectInfo, ProjectError, ProjectWarning, Rule
from .php import PHP_DEPRECATED, PHP_STABLE, PHP_UNSTABLE

log = logging.getLogger(__name__)

class GithubActionsOn(Rule):
    def active(self, project: Project) -> bool:
        return len(self.github_workflows(project)) != 0

    def check(self, project: Project) -> t.List[ProjectInfo]:
        infos: t.List[ProjectInfo] = []
        for wf in self.github_workflows(project):
            log.debug(f"Checking {wf.path}")
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
            log.debug(f"Checking {wf.path}")
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
            log.debug(f"Checking {wf.path}")
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
            log.debug(f"Checking {wf.path}")
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
            log.debug(f"Checking that {tool} is used in a workflow")
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
