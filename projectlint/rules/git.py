import logging
import subprocess
import typing as t
from pathlib import Path

from ..common import ProjectError, ProjectInfo, Rule

log = logging.getLogger(__name__)


class GitCleanWorkingTree(Rule):
    def active(self) -> bool:
        return (self.project.path / ".git").exists()

    def check_file(self, file: Path) -> t.Iterator[ProjectInfo]:
        try:
            # Run git diff to check for modified files
            # --exit-code returns 1 if there are differences, 0 if clean
            result = subprocess.run(
                ["git", "diff", "--exit-code"],
                cwd=self.project.path,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                # Get list of modified files for error message
                status_result = subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=self.project.path,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                # Filter for modified files only (lines starting with ' M' or 'M ')
                modified_files = []
                for line in status_result.stdout.splitlines():
                    if len(line) >= 2:
                        status = line[:2]
                        # ' M' = modified in working tree
                        # 'M ' = modified in index
                        # 'MM' = modified in both
                        if "M" in status:
                            filename = line[3:].strip()
                            modified_files.append(filename)

                if modified_files:
                    files_list = ", ".join(modified_files[:5])
                    if len(modified_files) > 5:
                        files_list += f" (and {len(modified_files) - 5} more)"

                    yield ProjectError(
                        f"Git working tree has modified files: {files_list}",
                        file=self.project.path,
                    )

        except subprocess.TimeoutExpired:
            log.warning("Git command timed out")
        except FileNotFoundError:
            log.warning("Git command not found")
        except Exception as e:
            log.warning(f"Error checking git status: {e}")
