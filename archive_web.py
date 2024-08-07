#!/usr/bin/env python

"""Moves the "web" folder into webdiffs, giving it a unique name to identify it"""

import argparse
import datetime
import inspect
import os
import shutil
import subprocess
import sys
import traceback

###############################################################################
# Constants
###############################################################################

THIS_FILE = os.path.abspath(inspect.getsourcefile(lambda: None) or __file__)
THIS_DIR = os.path.dirname(THIS_FILE)

if THIS_DIR not in sys.path:
    sys.path.append(THIS_DIR)

import luxtest_utils

WEB_DIR = os.path.join(THIS_DIR, "web")
WEB_ARCHIVE_DIR = os.path.join(THIS_DIR, "web.archive")

DEFAULT_USD_REPO = os.path.join(os.path.dirname(THIS_DIR), "usd-ci", "USD")
USD_REPO = os.environ.get("USD_ROOT", DEFAULT_USD_REPO)

###############################################################################
# Utilities
###############################################################################


def is_ipython():
    try:
        __IPYTHON__  # type: ignore
    except NameError:
        return False
    return True


def get_git_hash(repo_dir, n=8):
    proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_dir, text=True, capture_output=True)
    githash = proc.stdout.strip()
    if n:
        githash = githash[:n]
    return githash


###############################################################################
# Core functions
###############################################################################


def archive_web(name: str):
    now = datetime.datetime.now()
    date = now.strftime("%Y-%m-%d")
    luxtest_hash = get_git_hash(THIS_DIR)
    renders_hash = get_git_hash(luxtest_utils.get_renders_root())
    usd_hash = get_git_hash(USD_REPO)
    dest_name = f"{date}.{name}.luxtest-{luxtest_hash}.usd-{usd_hash}.renders-{renders_hash}"
    dest_path = os.path.join(WEB_ARCHIVE_DIR, dest_name)

    print("moving:")
    print(f"  {WEB_DIR}")
    print("to:")
    print(f"  {dest_path}")

    shutil.move(WEB_DIR, dest_path)


###############################################################################
# CLI
###############################################################################


def get_parser():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("name", help="short descriptive tag to help identify this set of diffs")
    return parser


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    parser = get_parser()
    args = parser.parse_args(argv)
    try:
        archive_web(name=args.name)
    except Exception:  # pylint: disable=broad-except

        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__" and not is_ipython():
    sys.exit(main())
