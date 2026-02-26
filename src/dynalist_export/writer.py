"""Smart file writer that tracks changes and supports git commit."""

import json
import logging
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any


def _raise(x: Exception) -> None:
    """Workaround for python's hate of one-liners."""
    raise x


class FileWriter:
    """Write output files in a smart way.

    - Do not override files if contents are the same.
    - Keep list of written files, remove pre-existing files which
      were not written this time.

    The behaviour is logically equivalent to doing "rm -r" on output dir, then writing
    output files -- but the ctime/inode does not change if the file contents did not change
    either.
    """

    def __init__(self, datadir: str | Path, dry_run: bool) -> None:
        self.datadir = str(Path(datadir).resolve())
        self.dry_run = dry_run
        self.logger = logging.getLogger("writer")

        if not dry_run and not Path(self.datadir).is_dir():
            msg = f"Data directory {self.datadir!r} not found"
            raise ValueError(msg)

        self.logger.debug(f"Writer ready, datadir {datadir!r}, dry_run {dry_run!r}")
        # Names generated before. Used to ensure non-overriding of files. Set of absolute paths.
        self._files_made: set[str] = set()

        self._unique_names: set[str] = set()

        # Change list, used for generating git commit messages.
        # list of (action, filename) tuples
        self._updates: list[tuple[str, str]] = []

        # A short-diff message, usable for git commit.
        # Set by finalize() function.
        self.short_diff_message: str | None = None

        self._num_same = 0
        self._num_changed = 0

    def check_git(self) -> None:
        """Make sure the output directory is a git repo. Raise if not."""
        git_dir = Path(self.datadir) / ".git"
        if not git_dir.is_dir():
            msg = f"Data directory {self.datadir!r} not found or does not have a git repo"
            raise ValueError(msg)

    def is_possible_output(self, fname: str) -> bool:
        """Check if a file is a possible output file.

        To prevent cleanup from deleting too much, we require each file we write
        to be matched by this function.

        If we run a cleanup, and we find a file which is not matched by this function,
        we abort entire cleanup and ask for user's help.
        """
        return fname.endswith(".json") or fname.endswith(".txt")

    def make_unique_name(self, base: str, *, suffix: str = "") -> str:
        """Generate unique filename or file prefix.

        Append numbers to "base" until (base + suffix) does not match any files made nor
        any previous result of this function.
        """
        unique_str = ""
        unique_count = 0
        while True:
            fname = str(Path(self.datadir) / (base + unique_str + suffix))
            if not fname.startswith(self.datadir + "/"):
                msg = f"Path escapes datadir: {fname!r}"
                raise ValueError(msg)
            if fname not in self._files_made and fname not in self._unique_names:
                break
            unique_count += 1
            unique_str = f"-{unique_count}"

        # We could add to self._files_made, but that'd mess up final stats.
        self._unique_names.add(fname)
        return base + unique_str

    def make_data_file(
        self,
        fname_rel: str,
        *,
        contents: str | None = None,
        data: Any = None,
    ) -> None:
        """Write contents to a file relative to the output directory.

        Args:
            fname_rel: Path relative to output directory.
            contents: String contents to write. If None, serialize data to json.
            data: Data to serialize as json. Mutually exclusive with contents.
        """
        if contents is None:
            contents = json.dumps(data, sort_keys=True, indent=4) + "\n"
        elif data is not None:
            msg = "Cannot specify both contents and data"
            raise ValueError(msg)
        if Path(fname_rel).is_absolute():
            msg = f"must be relative: {fname_rel!r}"
            raise ValueError(msg)

        fname = str(Path(self.datadir) / fname_rel)
        if not fname.startswith(self.datadir + "/"):
            msg = f"Path escapes datadir: {fname!r}"
            raise ValueError(msg)
        if not self.is_possible_output(fname):
            msg = f"Wanted to write {fname!r} but is_possible_output() returns False"
            raise ValueError(msg)

        self._files_made.add(fname)
        action = "create"
        try:
            with open(fname, encoding="utf-8") as f:
                if f.read() == contents:
                    self._num_same += 1
                    return
            self._num_changed += 1
            action = "update"
        except (FileNotFoundError, UnicodeDecodeError):
            pass

        self._updates.append((action, fname))

        if self.dry_run:
            self.logger.info(f"dry-run: would {action} {fname!r}")
        else:
            self.logger.debug(f"Writing ({action}) {fname!r}")
            Path(fname).parent.mkdir(parents=True, exist_ok=True)
            with open(fname, "w", encoding="utf-8") as f:
                f.write(contents)

    def try_read_json(self, fname_rel: str) -> Any | None:
        """Try to read json from given relative path.

        Returns:
            Json contents if file is found, None if file is not found.
            Raises on all other errors.
        """
        fname = str(Path(self.datadir) / fname_rel)
        try:
            with open(fname, encoding="utf-8") as f:
                contents = f.read()
        except FileNotFoundError:
            return None
        rj = json.loads(contents)
        # If we read None, it'll be ambiguous vs "file not found". We do not expect this
        # to happen, so raise.
        if rj is None:
            msg = f"try_read_json found None object in {fname_rel!r}"
            raise ValueError(msg)
        return rj

    def finalize(self, *, delete_others: bool = False) -> None:
        """Print update statistics.

        If delete_others is True, enumerate output location and remove
        all files not written this session.
        """
        if self.short_diff_message is not None:
            msg = "finalize() called twice"
            raise RuntimeError(msg)

        # Get list of files which can be potentially cleaned up.
        to_clean: list[str] = []
        suspicious: list[str] = []
        empty_dirs: set[str] = set()

        for dirpath, dirnames, filenames in os.walk(self.datadir, onerror=_raise):
            if ".git" in dirnames:
                dirnames.remove(".git")
            empty_dirs.update(str(Path(dirpath) / x) for x in dirnames)

            for fname in [str(Path(dirpath) / x) for x in filenames]:
                if fname in self._files_made:
                    continue
                to_clean.append(fname)
                self._updates.append(("delete", fname))
                if not self.is_possible_output(fname):
                    suspicious.append(fname)
        to_clean.sort()

        nonempty_dirs = {self.datadir}
        for dirpath_str in sorted({str(Path(x).parent) for x in self._files_made}):
            dn = dirpath_str
            while len(dn) > len(self.datadir):
                nonempty_dirs.add(dn)
                dn = str(Path(dn).parent)

        # For commit message, only .txt files matter
        # (and we only put basenames without extensions, too)
        last_action = None
        detailed_diff_tags: list[str] = []
        count_by_type: dict[str, int] = {}
        for action, fname in sorted(self._updates):
            if fname.endswith(".txt"):
                count_by_type[action] = count_by_type.get(action, 0) + 1
                msg_part = repr(Path(fname).stem)
                if action != last_action:
                    msg_part = f"{action} {msg_part}"
                    last_action = action
                detailed_diff_tags.append(msg_part)
            else:
                count_by_type["other"] = count_by_type.get("other", 0) + 1

        detailed_diff = ", ".join(detailed_diff_tags)
        if detailed_diff == "":
            self.short_diff_message = "no changes"
        elif len(detailed_diff) < 120 or len(detailed_diff_tags) <= 2:
            self.short_diff_message = detailed_diff
        else:
            # Message too long, just show counts
            self.short_diff_message = ", ".join(
                f"{action} {count}" for action, count in sorted(count_by_type.items())
            )

        # Remove empty dirs, starting from deepest filenames
        empty_dirs.difference_update(nonempty_dirs)
        to_clean += [x + "/" for x in sorted(empty_dirs, key=lambda x: (-x.count("/"), x))]

        log_msg = (
            f"Outputs: {self._num_same} same (in {len(nonempty_dirs)} folders), "
            f"{self._num_changed} changed, "
            f"{len(self._files_made) - self._num_same - self._num_changed} new, "
            f"{len(to_clean)} to-remove"
        )
        log_msg2 = f"Details: {detailed_diff}"
        if self._num_same == len(self._files_made):
            self.logger.debug(log_msg)
            self.logger.debug(log_msg2)
        else:
            self.logger.info(log_msg)
            self.logger.info(log_msg2)

        if suspicious:
            self.logger.warning(
                f"Found suspicious files in output dir ({len(suspicious)}), cleanup disabled: "
                f"{' '.join(map(shlex.quote, sorted(suspicious)[:10]))}"
            )

        if not to_clean:
            self.logger.debug("Nothing to clean up")
        elif delete_others:
            if suspicious:
                raise SystemExit(f"FATAL: Cannot cleanup: {len(suspicious)} suspicious files")
            self.logger.info(f"Deleting {len(to_clean)} old file(s)")
            if to_clean:
                self.logger.debug(f".. some names to clean: {to_clean[:5]!r}")
            for fname in to_clean:
                if self.dry_run:
                    self.logger.info(f"dry-run: would remove {fname!r}")
                elif fname.endswith("/"):
                    self.logger.debug(f"Removing dir: {fname!r}")
                    Path(fname).rmdir()
                else:
                    self.logger.debug(f"Removing file: {fname!r}")
                    Path(fname).unlink()

    def git_commit(self, *, dry_run: bool) -> None:
        """If there are any changes, commit them."""
        changes = (
            subprocess.check_output(
                ["git", "status", "--porcelain"],
                cwd=self.datadir,
            )
            .decode("utf-8")
            .splitlines()
        )
        if not changes:
            self.logger.debug("git up to date, not committing")
            return
        self.logger.debug(f"git status returned {len(changes)} lines")

        cmd = ["git", "add", "--all"]
        if dry_run:
            cmd += ["--dry-run"]
        cmd += ["--", "."]
        self.logger.debug(f"Running: {' '.join(map(shlex.quote, cmd))}")
        subprocess.check_call(cmd, cwd=self.datadir)

        message = self.short_diff_message
        cmd = ["git", "commit", "-m", message or "", "--quiet"]
        if dry_run:
            cmd += ["--dry-run", "--short"]
        self.logger.debug(f"Running: {' '.join(map(shlex.quote, cmd))}")
        subprocess.check_call(cmd, cwd=self.datadir)

        self.logger.info(f"Made a git commit: {message}")
