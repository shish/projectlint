import abc
import logging
import re
import typing as t
from pathlib import Path

import yaml

log = logging.getLogger(__name__)


class Project:
    def __init__(self, path: Path, ignore_paths: t.Optional[t.List[str]] = None):
        self.path = path
        self.ignore_paths = ignore_paths or []


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
    def __init__(self, project: Project):
        self.project = project

    @abc.abstractmethod
    def active(self) -> bool: ...

    @abc.abstractmethod
    def check(self) -> t.Iterable[ProjectInfo]: ...

    def find_files(self, pattern: str) -> t.Iterable[Path]:
        return [
            p
            for p in self.project.path.rglob(pattern)
            if not any(p.parts[i] in self.project.ignore_paths for i in range(len(p.parts)))
        ]


class FileRule(Rule):
    RELEVANT_PATTERNS = []

    def __init__(self, project: Project):
        super().__init__(project)
        self.relevant_paths = []
        for pattern in self.RELEVANT_PATTERNS:
            for file in self.find_files(pattern):
                self.relevant_paths.append(file)

    def active(self) -> bool:
        return bool(self.relevant_paths)

    def check(self) -> t.Iterator[ProjectInfo]:
        for path in self.relevant_paths:
            log.debug(f"...check_file({path})")
            yield from self.check_file(path)

    @abc.abstractmethod
    def check_file(self, file: Path) -> t.Iterator[ProjectInfo]: ...


class Versions:
    DEPRECATED: t.List[str]
    STABLE: t.List[str]
    UNSTABLE: t.List[str]


def satisfies_constraint(actual: str, required: str, exact_match: bool = False) -> bool:
    """
    Check if an actual version constraint satisfies a required constraint.

    Args:
        actual: The actual version constraint found in the file
        required: The required version constraint from the rule
        exact_match: If True, only allow exact string matches (for non-semantic versions)

    Returns:
        True if the actual constraint satisfies the required constraint

    Examples:
        >>> satisfies_constraint("^12.5", "^12.1")  # True - higher minor version
        >>> satisfies_constraint("^12.0", "^12.1")  # False - lower minor version
        >>> satisfies_constraint("^11.5", "^12.1")  # False - different major version
        >>> satisfies_constraint("stable", "stable", exact_match=True)  # True
        >>> satisfies_constraint("trixie", "stable", exact_match=True)  # False
    """
    # Handle exact matches first
    if actual == required:
        return True

    # If exact_match is required, don't do any fuzzy matching
    if exact_match:
        return False

    # Parse caret constraints (e.g., ^12.1)
    caret_pattern = r"^\^(\d+)\.(\d+)(?:\.(\d+))?$"
    actual_match = re.match(caret_pattern, actual)
    required_match = re.match(caret_pattern, required)

    if actual_match and required_match:
        # Extract version parts
        actual_major = int(actual_match.group(1))
        actual_minor = int(actual_match.group(2))
        actual_patch = int(actual_match.group(3) or 0)

        required_major = int(required_match.group(1))
        required_minor = int(required_match.group(2))
        required_patch = int(required_match.group(3) or 0)

        # Both must have the same major version for caret constraint
        if actual_major != required_major:
            return False

        # Actual constraint satisfies required if it's >= in the minor.patch version
        # ^12.5 satisfies ^12.1 because 12.5 >= 12.1
        # Compare as tuples for proper version comparison
        actual_ver = (actual_major, actual_minor, actual_patch)
        required_ver = (required_major, required_minor, required_patch)

        return actual_ver >= required_ver

    # Check if actual version starts with required (for simple version prefixes)
    # e.g., "1.94.2" starts with "1.94"
    if actual.startswith(required):
        return True

    # If we can't parse or they're different constraint types, fall back to string comparison
    return False
