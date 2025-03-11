import json
import typing as t
from pathlib import Path

from ..common import ProjectInfo, ProjectError, ProjectWarning, FileRule, Versions


# https://www.php.net/supported-versions.php
class PHPVersions(Versions):
    DEPRECATED = ["7", "8.0", "8.1"]
    STABLE = ["8.2", "8.3", "8.4"]
    UNSTABLE = []
    PLATFORM = "8.2.0"


class PHPComposerPlatform(FileRule):
    RELEVANT_PATTERNS = ["composer.json"]

    def check_file(self, file: Path) -> t.Iterator[ProjectInfo]:
        data = json.load(file.open())

        php_version = data.get("config", {}).get("platform", {}).get("php")
        if php_version is not None and php_version != PHPVersions.PLATFORM:
            yield ProjectWarning(
                f"should be {PHPVersions.PLATFORM}, is {php_version}",
                file=file,
                position="config.platform.php",
            )


class PHPComposerDeps(FileRule):
    RELEVANT_PATTERNS = ["composer.json"]

    def check_file(self, file: Path) -> t.Iterator[ProjectInfo]:
        data = json.load(file.open())

        # we should support "oldest supported PHP version" and newer
        if "require" not in data:
            yield ProjectWarning(
                "No dependencies are required, should at least require php",
                file=file,
            )
        elif "php" not in data["require"]:
            yield ProjectWarning(
                "PHP should be required", file=file, position="require"
            )
        else:
            php_version = data["require"]["php"]
            if php_version != f"^{PHPVersions.STABLE[0]}":
                yield ProjectWarning(
                    f"should be ^{PHPVersions.STABLE[0]}, is {php_version}",
                    file=file,
                    position="require.php",
                )

        # dev tools should be current
        if "require-dev" not in data:
            yield ProjectWarning(
                "No dev dependencies are required, should at least require phpunit",
                file=file,
            )

        else:
            for (tool, stable, config) in [
                ("phpunit/phpunit", "^11.0", "phpunit.xml.dist"),
                ("phpstan/phpstan", "^2.0", "phpstan.neon.dist"),
                ("friendsofphp/php-cs-fixer", "^3.64", ".php-cs-fixer.dist.php"),
            ]:
                if tool not in data["require-dev"]:
                    yield ProjectWarning(
                        f"{tool} should be required",
                        file=file,
                        position="require-dev",
                    )

                else:
                    version = data["require-dev"][tool]
                    if version != stable:
                        yield ProjectWarning(
                            f"should be {stable}, is {version}",
                            file=file,
                            position=f"require-dev.{tool}",
                        )
                    if not (file.parent / config).exists():
                        yield ProjectWarning(
                            f"{config} should be present",
                            file=file,
                            position=f"require-dev.{tool}",
                        )


class PHPComposerLock(FileRule):
    RELEVANT_PATTERNS = ["composer.lock"]

    def check_file(self, file: Path) -> t.Iterator[ProjectInfo]:
        # check that composer.lock is up to date with composer.json
        json_modified = file.with_suffix(".json").stat().st_mtime
        lock_modified = file.stat().st_mtime
        if json_modified > lock_modified:
            yield ProjectError("composer.lock is out of date", file=file)
