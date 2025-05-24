#!/usr/bin/env python3
#
# This tool requires "Full Disk Access" to query Time Machine information!
#
import argparse
import asyncio
import hashlib
import os
import subprocess
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional
from unittest import case

TMP_DISKUSAGE_PATH = Path.home() / "tmp"
SCRIPT_NAME = Path(__file__).stem

def now():
    return datetime.now(tz=timezone.utc)


async def wait_for_path_content(path: Path):
    while True:
        print(f"Waiting for files in {path}...")
        if len(list(path.glob("*"))):
            return
        await asyncio.sleep(1)


async def load_disk_usage(path: Path) -> Dict[str, int]:
    print(f"Loading disk usage for {path}")
    path_hash = hashlib.sha256(str(path).encode("utf8")).hexdigest()
    cache_path = TMP_DISKUSAGE_PATH / f"{SCRIPT_NAME}-cache-{path_hash}.txt"
    if cache_path.exists():
        print(f"Using cached disk usage of {path}")
        data = cache_path.read_text(encoding="utf8")
    else:
        # Somehow files in the time machine backup are only visible for us,
        # after we have opened a 'Finder' window for that path !?
        # Not sure if it needs to stay open while our 'du' command runs !?
        print(f"Starting 'Finder' for {path}")
        process = await asyncio.create_subprocess_exec("open", path)
        await process.communicate()

        try:
            async with asyncio.timeout(5):
                await wait_for_path_content(path)
        except TimeoutError:
            raise RuntimeError(
                f"Backup directory not visible, maybe try to open it in Finder manually and retry: {path}"
            )

        print(f"Using 'du' for disk usage of {path}...")
        process = await asyncio.create_subprocess_exec(
            "du", "-k", ".", stdout=subprocess.PIPE, cwd=path
        )
        stdout, stderr = await process.communicate()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(stdout)
        data = stdout.decode("utf8")
    size_by_path = dict()
    for line in data.splitlines():
        size, path = line.split(maxsplit=1)
        size_by_path[path] = int(size)
    return size_by_path


async def is_included(path: str) -> bool:
    process = await asyncio.create_subprocess_exec(
        "tmutil", "isexcluded", Path.home() / path, stdout=subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    output = stdout.decode("utf8")
    if output.lower().startswith("[included] ") or output.lower().startswith(
        "[unknown] "
    ):
        return True
    if output.lower().startswith("[excluded] "):
        return False
    raise ValueError(f"Unknown tmutil output: {output}")


class Order(Enum):
    PATH = "PATH"
    SIZE = "SIZE"


class Change(Enum):
    NEW = "NEW"
    REMOVED = "REMOVED"
    CHANGED = "CHANGED"


@dataclass
class ChangeDescription:
    type: Change
    size: int
    path: str

    def __str__(self):
        return f"{self.type.name:>7} {self.size:>8d} {self.path}"


async def compare_disk_usage(
    left_size_by_path: Dict[str, int],
    right_size_by_path: Dict[str, int],
    order: Order = Order.PATH,
    limit: Optional[int] = None,
):
    left_paths = set(left_size_by_path.keys())
    right_paths = set(right_size_by_path.keys())
    same_paths = left_paths.intersection(right_paths)
    only_left_paths = left_paths - right_paths
    only_right_paths = right_paths - left_paths
    changes: List[ChangeDescription] = []
    for path in only_left_paths:
        size = left_size_by_path[path]
        if size:
            changes.append(
                ChangeDescription(type=Change.REMOVED, size=-size, path=path)
            )
    for path in only_right_paths:
        size = right_size_by_path[path]
        if size:
            changes.append(ChangeDescription(type=Change.NEW, size=size, path=path))
    for path in same_paths:
        left_size = left_size_by_path[path]
        right_size = right_size_by_path[path]
        diff_size = right_size - left_size
        if diff_size:
            changes.append(
                ChangeDescription(type=Change.CHANGED, size=diff_size, path=path)
            )
    match order:
        case Order.PATH:
            changes = sorted(changes, key=lambda change: change.path)
        case Order.SIZE:
            changes = sorted(changes, key=lambda change: change.size, reverse=True)
        case _:
            raise RuntimeError(f"Unknown order: {order}")
    limit_hint = f" ( only the first {limit} changes )" if limit else ""
    limit = limit or len(changes)
    print(f"Differences in 1k blocks{limit_hint}:")
    for change in changes[:limit]:
        print(change)
    print(f"CHANGED {sum([c.size for c in changes]):>8d} TOTAL")


async def get_user_home_backup_paths() -> List[Path]:
    process = await asyncio.create_subprocess_exec(
        "tmutil", "listbackups", stdout=subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    return [
        Path(p) / "Data" / "Users" / os.environ["USER"]
        for p in stdout.decode("utf8").splitlines()
    ]


async def main(backup_idx: Optional[int], order: Order, limit: int) -> int:
    print("Searching for backups...")
    user_home_backup_paths = await get_user_home_backup_paths()
    if not user_home_backup_paths:
        return 1
    for i, p in enumerate(user_home_backup_paths):
        print(f"{i:>3d} {p}")
    if backup_idx is None:
        print(
            "Select backup index to diff with predecessor, e.g use '-1' for the last backup."
        )
        return 1
    left_path = user_home_backup_paths[backup_idx - 1]
    right_path = user_home_backup_paths[backup_idx]
    print(f"Analysing differences between\n  {left_path}\nand\n  {right_path}")
    left_size_by_path, right_size_by_path = await asyncio.gather(
        load_disk_usage(left_path), load_disk_usage(right_path), return_exceptions=True
    )
    if isinstance(left_size_by_path, Exception):
        traceback.print_exception(left_size_by_path)
    if isinstance(right_size_by_path, Exception):
        traceback.print_exception(right_size_by_path)
    if isinstance(left_size_by_path, Exception) or isinstance(
        right_size_by_path, Exception
    ):
        return 1
    await compare_disk_usage(
        left_size_by_path, right_size_by_path, order=order, limit=limit
    )
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog=Path(sys.argv[0]).name,
        description="Analyse differences between Time Machine backups.",
    )
    parser.add_argument(
        "--backup-idx",
        type=int,
        default=None,
        help="Analyse backup at index with its predecessor. Default will just show all available backups.",
        metavar="IDX",
    )
    parser.add_argument(
        "--order",
        type=str,
        default="PATH",
        choices=["PATH", "SIZE"],
        help="Order output of changes by selected criteria. Default is 'PATH'.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Only output up to given number of changes.",
    )
    parser.add_argument(
        "--cache",
        type=str,
        default=TMP_DISKUSAGE_PATH,
        metavar="PATH",
        help=f"Use given directory to cache disk usage details of backups. Default is '{TMP_DISKUSAGE_PATH}'.",
    )
    args = parser.parse_args()
    loop = asyncio.new_event_loop()
    order = next(o for o in Order if o.name == args.order)
    TMP_DISKUSAGE_PATH = Path(args.cache)
    exitcode = loop.run_until_complete(
        main(
            args.backup_idx,
            order,
            args.limit,
        )
    )
    sys.exit(exitcode)
