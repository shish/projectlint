#!/usr/bin/env python3

import argparse
import sys
import typing as t
from pathlib import Path
import logging

from .common import Project, ProjectInfo, ProjectError, ProjectWarning, Rule

from .rules.github import *
from .rules.php import *


log = logging.getLogger(__name__)


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
