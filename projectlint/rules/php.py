import json
import typing as t

from ..common import Project, ProjectInfo, ProjectError, ProjectWarning, Rule


# https://www.php.net/supported-versions.php
PHP_DEPRECATED = ["7", "8.0", "8.1"]
PHP_STABLE = ["8.2", "8.3"]
PHP_UNSTABLE = ["8.4"]


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
