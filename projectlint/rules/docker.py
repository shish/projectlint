import typing as t
from pathlib import Path

from ..common import FileRule, ProjectError, ProjectInfo, satisfies_constraint


class DockerBaseImages(FileRule):
    RELEVANT_PATTERNS = ["Dockerfile"]
    EXPECTED_IMAGES = {
        "debian": ["trixie", "stable", "stable-slim"],  # stable, testing
        "ubuntu": ["24.04", "noble"],
    }
    # Images that use named versions (must be exact match)
    EXACT_MATCH_IMAGES = {"debian", "ubuntu"}

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
            if pkg in self.EXPECTED_IMAGES:
                # Determine if we should use exact matching or semantic versioning
                use_exact_match = pkg in self.EXACT_MATCH_IMAGES

                # Check if the version satisfies any of the expected versions
                if not any(
                    satisfies_constraint(ver, v, exact_match=use_exact_match) for v in self.EXPECTED_IMAGES[pkg]
                ):
                    yield ProjectError(
                        f"{pkg} should be {self.EXPECTED_IMAGES[pkg]}, is {ver}",
                        file=file,
                    )
