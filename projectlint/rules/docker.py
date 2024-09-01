import json
import typing as t
from pathlib import Path

from ..common import Project, ProjectInfo, ProjectError, ProjectWarning, FileRule


class DockerBaseImages(FileRule):
    RELEVANT_PATTERNS = ["Dockerfile"]
    EXPECTED_IMAGES = {
        "python": ["3.12"],
        "debian": ["bookworm", "stable"],
        "ubuntu": ["24.04", "noble"],
    }

    def check_file(self, file: Path) -> t.Iterator[ProjectInfo]:
        internal_tags = []

        for line in file.open().readlines():
            if not line.startswith("FROM "):
                continue
            image = line.split()[1]
            if "AS" in line:
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
            if pkg in self.EXPECTED_IMAGES and not any(
                ver.startswith(v) for v in self.EXPECTED_IMAGES[pkg]
            ):
                yield ProjectError(
                    f"{pkg} should be {self.EXPECTED_IMAGES[pkg]}, is {ver}",
                    file=file,
                )
