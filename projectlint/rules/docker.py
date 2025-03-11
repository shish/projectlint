import typing as t
from pathlib import Path

from ..common import ProjectInfo, ProjectError, FileRule
from . import js
from . import python

class DockerBaseImages(FileRule):
    RELEVANT_PATTERNS = ["Dockerfile"]
    EXPECTED_IMAGES = {
        "node": js.NodeVersions.STABLE + js.NodeVersions.UNSTABLE,
        "python": python.PythonVersions.STABLE + python.PythonVersions.UNSTABLE,
        "rust": ["1.80"],
        "debian": ["bookworm", "stable"],
        "ubuntu": ["24.04", "noble"],
    }

    def check_file(self, file: Path) -> t.Iterator[ProjectInfo]:
        internal_tags = []

        for line in file.open().readlines():
            if not line.startswith("FROM "):
                continue
            image = line.split()[1]
            if " AS " in line.upper():
                internal_tags.append(line.split(" ")[3].strip())

            if ":" not in image:
                if image in internal_tags:
                    continue
                yield ProjectError(
                    f"Image should have a tag, is {image} ({internal_tags})",
                    file=file,
                )
                continue

            pkg, ver = image.split(":")
            if ver.startswith("$"):
                # can't currently check for dynamic tags
                continue
            if pkg in self.EXPECTED_IMAGES and not any(
                ver.startswith(v) for v in self.EXPECTED_IMAGES[pkg]
            ):
                yield ProjectError(
                    f"{pkg} should be {self.EXPECTED_IMAGES[pkg]}, is {ver}",
                    file=file,
                )
