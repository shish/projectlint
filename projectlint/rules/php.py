import json
import typing as t
from pathlib import Path

from ..common import FileRule, ProjectError, ProjectInfo, ProjectWarning, Versions, satisfies_constraint


# https://www.php.net/supported-versions.php
class PHPVersions(Versions):
    DEPRECATED = ["7", "8.0", "8.1", "8.2", "8.3"]
    STABLE = ["8.4", "8.5"]
    UNSTABLE = []
    PLATFORM = "8.4.0"


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


class PHPComposerScripts(FileRule):
    RELEVANT_PATTERNS = ["composer.json"]

    def check_file(self, file: Path) -> t.Iterator[ProjectInfo]:
        data = json.load(file.open())

        scripts = data.get("scripts", {})

        if scripts.get("check") != ["@format", "@analyse", "@test"]:
            yield ProjectWarning(
                'check script should be ["@format", "@analyse", "@test"]',
                file=file,
                position="scripts.check",
            )

        if scripts.get("format") != "php-cs-fixer fix":
            yield ProjectWarning(
                'format script should be "php-cs-fixer fix"',
                file=file,
                position="scripts.format",
            )

        if scripts.get("analyse") not in [
            "phpstan analyse --error-format=raw | sed -E 's/:([0-9]+):/:\\1 /'",
            "phpstan analyse --memory-limit 1G --error-format=raw | sed -E 's/:([0-9]+):/:\\1 /'",
        ]:
            yield ProjectWarning(
                "analyse script should be \"phpstan analyse --error-format=raw | sed -E 's/:([0-9]+):/:\\1 /'\"",
                file=file,
                position="scripts.analyse",
            )

        if scripts.get("test") != "php -d xdebug.mode=coverage vendor/bin/phpunit":
            yield ProjectWarning(
                'test script should be "php -d xdebug.mode=coverage vendor/bin/phpunit"',
                file=file,
                position="scripts.test",
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
            yield ProjectWarning("PHP should be required", file=file, position="require")
        else:
            php_version = data["require"]["php"]
            required_php = f"^{PHPVersions.STABLE[0]}"
            if not satisfies_constraint(php_version, required_php):
                yield ProjectWarning(
                    f"should be {required_php}, is {php_version}",
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
            for tool, stables, config in [
                ("phpunit/phpunit", ["^11.5", "^12.1"], "phpunit.dist.xml"),
                ("phpstan/phpstan", "^2.1", "phpstan.dist.neon"),
                ("friendsofphp/php-cs-fixer", "^3.89", ".php-cs-fixer.dist.php"),
            ]:
                if tool not in data["require-dev"]:
                    yield ProjectWarning(
                        f"{tool} should be required",
                        file=file,
                        position="require-dev",
                    )

                else:
                    version = data["require-dev"][tool]
                    # Normalize stables to always be a list
                    stables_list = stables if isinstance(stables, list) else [stables]
                    # Check if the actual version satisfies any of the required constraints
                    if not any(satisfies_constraint(version, stable) for stable in stables_list):
                        yield ProjectWarning(
                            f"should be in {stables}, is {version}",
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
        # if composer.lock is in .gitignore, skip the check
        gitignore = file.parent / ".gitignore"
        if gitignore.exists():
            if "composer.lock" in gitignore.read_text():
                return

        # check that composer.lock is up to date with composer.json
        json_modified = file.with_suffix(".json").stat().st_mtime
        lock_modified = file.stat().st_mtime
        if json_modified > lock_modified:
            yield ProjectError("composer.lock is out of date", file=file)
