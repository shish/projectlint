import logging
import typing as t

import yaml

from ..common import ProjectInfo, ProjectWarning, Rule

log = logging.getLogger(__name__)


class BaseDependabotRule(Rule):
    """Base class for checking dependabot configuration for different package ecosystems"""

    # Subclasses should override these
    PACKAGE_ECOSYSTEM: str = ""  # e.g., "github-actions", "composer", "npm"
    TRIGGER_PATTERNS: t.List[str] = []  # Files that trigger this rule, e.g., ["composer.json"]
    SCHEDULE_INTERVAL: str = "monthly"  # Update interval
    FORCE_ROOT_DIRECTORY: bool = False  # If True, always use "/" regardless of trigger file location

    def active(self) -> bool:
        """Active if any trigger files exist"""
        return (
            len(self._get_expected_directories()) > 0
            # and self.project.path.joinpath(".github", "dependabot.yml").exists()
        )

    def _get_expected_directories(self) -> t.Set[str]:
        """Get the set of directories that should be monitored based on trigger files"""
        # Some ecosystems (like github-actions) always monitor root regardless of file location
        if self.FORCE_ROOT_DIRECTORY:
            for pattern in self.TRIGGER_PATTERNS:
                if list(self.find_files(pattern)):
                    return {"/"}
            return set()

        directories = set()
        for pattern in self.TRIGGER_PATTERNS:
            for file_path in self.find_files(pattern):
                # Get directory relative to project root
                relative_path = file_path.relative_to(self.project.path)
                directory = "/" + str(relative_path.parent) if relative_path.parent.parts else "/"
                # Normalize to use forward slashes and remove trailing slashes
                directory = directory.replace("\\", "/").rstrip("/")
                # Ensure root is always just "/"
                if not directory:
                    directory = "/"
                directories.add(directory)
        return directories

    def check(self) -> t.Iterator[ProjectInfo]:
        """Check that dependabot.yml contains the expected configuration"""
        dependabot_file = self.project.path / ".github" / "dependabot.yml"

        expected_directories = self._get_expected_directories()
        if not expected_directories:
            # No trigger files found, rule should be inactive
            return

        if not dependabot_file.exists():
            dirs_list = ", ".join(sorted(expected_directories))
            yield ProjectWarning(
                f"dependabot.yml should exist to monitor {self.PACKAGE_ECOSYSTEM} in {dirs_list}",
                file=dependabot_file,
            )
            return

        # Load and check dependabot configuration
        try:
            with dependabot_file.open() as f:
                config = yaml.safe_load(f)

            if not config or "updates" not in config:
                yield ProjectWarning(
                    "dependabot.yml should contain 'updates' section",
                    file=dependabot_file,
                )
                return

            # Find all configured directories for this ecosystem
            configured_directories = set()
            for update in config.get("updates", []):
                if update.get("package-ecosystem") == self.PACKAGE_ECOSYSTEM:
                    # Support both "directory" (single string) and "directories" (list of strings)
                    directories_to_process = []
                    if "directories" in update:
                        directories_value = update["directories"]
                        if isinstance(directories_value, list):
                            directories_to_process = directories_value
                        else:
                            # If "directories" exists but isn't a list, treat as single value
                            directories_to_process = [directories_value]
                    elif "directory" in update:
                        directories_to_process = [update["directory"]]
                    else:
                        # Default to root if neither is specified
                        directories_to_process = ["/"]

                    for directory in directories_to_process:
                        # Normalize directory: remove trailing slash unless it's root
                        directory = directory.rstrip("/")
                        if not directory:
                            directory = "/"
                        configured_directories.add(directory)

                    # Check schedule interval
                    schedule = update.get("schedule", {})
                    if schedule.get("interval") != self.SCHEDULE_INTERVAL:
                        for directory in directories_to_process:
                            directory = directory.rstrip("/") or "/"
                            yield ProjectWarning(
                                f"{self.PACKAGE_ECOSYSTEM} ({directory}) schedule interval should be '{self.SCHEDULE_INTERVAL}', is '{schedule.get('interval')}'",
                                file=dependabot_file,
                                position=f"updates[package-ecosystem={self.PACKAGE_ECOSYSTEM},directory={directory}].schedule.interval",
                            )

            # Check for missing directories
            missing_directories = expected_directories - configured_directories
            for directory in sorted(missing_directories):
                yield ProjectWarning(
                    f"dependabot.yml should contain update for '{self.PACKAGE_ECOSYSTEM}' in directory '{directory}'",
                    file=dependabot_file,
                    position="updates",
                )

            # Check for unexpected directories (directories that don't have trigger files)
            unexpected_directories = configured_directories - expected_directories
            for directory in sorted(unexpected_directories):
                yield ProjectWarning(
                    f"dependabot.yml has update for '{self.PACKAGE_ECOSYSTEM}' in '{directory}' but no trigger file found there",
                    file=dependabot_file,
                    position="updates",
                )

        except yaml.YAMLError as e:
            yield ProjectWarning(
                f"dependabot.yml is not valid YAML: {e}",
                file=dependabot_file,
            )
        except Exception as e:
            log.warning(f"Error checking dependabot.yml: {e}")


class DependabotGithubActions(BaseDependabotRule):
    """Check that dependabot monitors GitHub Actions"""

    PACKAGE_ECOSYSTEM = "github-actions"
    TRIGGER_PATTERNS = [".github/workflows/*.yml", ".github/workflows/*.yaml"]
    FORCE_ROOT_DIRECTORY = True  # GitHub Actions always monitors root


class DependabotComposer(BaseDependabotRule):
    """Check that dependabot monitors Composer dependencies"""

    PACKAGE_ECOSYSTEM = "composer"
    TRIGGER_PATTERNS = ["composer.json"]


class DependabotNpm(BaseDependabotRule):
    """Check that dependabot monitors npm dependencies"""

    PACKAGE_ECOSYSTEM = "npm"
    TRIGGER_PATTERNS = ["package.json"]


class DependabotPip(BaseDependabotRule):
    """Check that dependabot monitors Python pip dependencies"""

    PACKAGE_ECOSYSTEM = "pip"
    TRIGGER_PATTERNS = ["requirements.txt", "requirements*.txt", "pyproject.toml"]


class DependabotCargo(BaseDependabotRule):
    """Check that dependabot monitors Cargo dependencies"""

    PACKAGE_ECOSYSTEM = "cargo"
    TRIGGER_PATTERNS = ["Cargo.toml"]


class DependabotDocker(BaseDependabotRule):
    """Check that dependabot monitors Docker dependencies"""

    PACKAGE_ECOSYSTEM = "docker"
    TRIGGER_PATTERNS = ["Dockerfile", "Dockerfile.*", "**/Dockerfile"]
