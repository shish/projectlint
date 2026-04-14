#!/usr/bin/env python3

# ruff: noqa: F403
#
import argparse
import cProfile
import inspect
import logging
import pstats
import sys
import time
import typing as t
from pathlib import Path

import yaml

from .common import Project, ProjectError, ProjectWarning, Rule
from .rules.dependabot import *
from .rules.docker import *
from .rules.git import *
from .rules.github import *
from .rules.js import *
from .rules.php import *
from .rules.python import *
from .rules.rust import *

log = logging.getLogger(__name__)


def get_subclasses(cls: t.Type[t.Any]) -> t.List[t.Type[t.Any]]:
    return cls.__subclasses__() + [g for s in cls.__subclasses__() for g in get_subclasses(s)]


def get_rules() -> t.List[t.Type[Rule]]:
    return [r for r in get_subclasses(Rule) if not inspect.isabstract(r)]


def main(argv: t.Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description="Lint a project")
    parser.add_argument("projects", help="The project(s) to lint", type=Path, nargs="+", metavar="project")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show verbose output")
    parser.add_argument("--config", "-c", help="Path to config file", type=Path)
    parser.add_argument("--profile", "-p", action="store_true", help="Enable profiling and show timing information")
    args = parser.parse_args(argv[1:])

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if args.profile:
        return run_with_profiling(args)
    else:
        return run_normal(args)


def run_with_profiling(args: argparse.Namespace) -> int:
    """Run with profiling enabled and show timing breakdown"""
    profiler = cProfile.Profile()
    profiler.enable()

    start_time = time.time()
    result = run_normal(args, profile_mode=True)
    total_time = time.time() - start_time

    profiler.disable()

    print("\n" + "=" * 80)
    print("PROFILING RESULTS")
    print("=" * 80)
    print(f"\nTotal execution time: {total_time:.3f}s\n")

    # Show top time-consuming functions
    stats = pstats.Stats(profiler)
    stats.strip_dirs()
    stats.sort_stats("cumulative")

    print("Top 30 functions by cumulative time:")
    print("-" * 80)
    stats.print_stats(30)

    print("\nTop 30 functions by total time:")
    print("-" * 80)
    stats.sort_stats("tottime")
    stats.print_stats(30)

    return result


def run_normal(args: argparse.Namespace, profile_mode: bool = False) -> int:
    """Normal execution with optional timing information"""
    timings = {}

    def timed_section(name: str):
        """Context manager for timing sections"""

        class TimedSection:
            def __enter__(self):
                self.start = time.time()
                return self

            def __exit__(self, *args):
                timings[name] = time.time() - self.start

        return TimedSection()

    with timed_section("setup"):
        config = {}
        if args.config and args.config.exists():
            log.info(f"Loading config from {args.config}")
            config = yaml.safe_load(args.config.read_text())

    with timed_section("get_rules"):
        rule_subclasses: t.List[t.Type[Rule]] = get_rules()

    fail = False
    baseline_issues = set(config.get("baseline", []))

    # Process each project
    for project_path in args.projects:
        project_name = project_path.name

        log.debug(f"Linting project {project_path}")

        with timed_section(f"setup_{project_name}"):
            project = Project(project_path, config.get("ignore_paths"))

        with timed_section(f"instantiate_rules_{project_name}"):
            rules: t.List[Rule] = []
            for r in rule_subclasses:
                rule_start = time.time()
                log.debug(f"Instantiating {r.__name__} for {project_name}...")
                rule_instance = r(project)
                rule_time = time.time() - rule_start
                if rule_time > 0.1:
                    log.info(f"  {r.__name__} took {rule_time:.3f}s to instantiate")
                rules.append(rule_instance)

        with timed_section(f"check_rules_{project_name}"):
            for rule in rules:
                rule_name = rule.__class__.__name__

                if not rule.active():
                    log.debug(f"Skipping {rule_name} for {project_name}")
                    continue

                rule_start = time.time()
                log.debug(f"{rule_name}.check() for {project_name}")
                infos = rule.check()
                for info in infos:
                    if isinstance(info, ProjectError):
                        msg = f"Error: {project_name}: {info.file}:{info.position}: {info.message}"
                        fail = True
                    elif isinstance(info, ProjectWarning):
                        msg = f"Warning: {project_name}: {info.file}:{info.position}: {info.message}"
                    else:
                        msg = f"Info: {project_name}: {info.file}:{info.position}: {info.message}"
                    if msg not in baseline_issues:
                        print(msg)

                rule_time = time.time() - rule_start
                timings[f"rule_{project_name}_{rule_name}"] = rule_time

    if profile_mode:
        print("\n" + "=" * 80)
        print("TIMING BREAKDOWN")
        print("=" * 80)

        print(f"\nSetup: {timings.get('setup', 0):.3f}s")
        print(f"Get rules: {timings.get('get_rules', 0):.3f}s")

        # Group timings by project
        for project_path in args.projects:
            project_name = project_path.name
            print(f"\nProject: {project_name}")
            print(f"  Setup: {timings.get(f'setup_{project_name}', 0):.3f}s")
            print(f"  Instantiate rules: {timings.get(f'instantiate_rules_{project_name}', 0):.3f}s")
            print(f"  Check rules (total): {timings.get(f'check_rules_{project_name}', 0):.3f}s")

            print("\n  Per-rule timings:")
            rule_timings = [(k, v) for k, v in timings.items() if k.startswith(f"rule_{project_name}_")]
            rule_timings.sort(key=lambda x: x[1], reverse=True)
            for rule_key, rule_time in rule_timings:
                # Extract rule name from "rule_{project_name}_{rule_name}"
                rule_name = rule_key[len(f"rule_{project_name}_") :]
                print(f"    {rule_name}: {rule_time:.3f}s")

    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
