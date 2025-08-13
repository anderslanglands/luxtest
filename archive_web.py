# no hashbang - use .sh wrapper script

"""Moves the "web" folder into web.archive, giving it a unique name to identify it"""

import argparse
import datetime
import enum
import inspect
import os
import shlex
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
WEB_ARCHIVE_DIRNAME = "web.archive"

DEFAULT_USD_REPO = os.path.join(os.path.dirname(THIS_DIR), "usd-ci", "USD")
USD_REPO = os.environ.get("USD_ROOT", DEFAULT_USD_REPO)

DEFAULT_REMOTE_NAME = "origin"

###############################################################################
# Utilities
###############################################################################


class PushType(enum.Enum):
    OFF = 0
    ON = 1
    PRINT = 2

    @classmethod
    def from_str(cls, name: str):
        return getattr(cls, name.upper())


def is_ipython():
    try:
        __IPYTHON__  # type: ignore
    except NameError:
        return False
    return True


def get_git_hash(repo_dir: str):
    proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_dir, text=True, capture_output=True, check=True)
    githash = proc.stdout.strip()
    return githash


def git_tag(repo_dir: str, tag_name: str, commit="HEAD"):
    subprocess.run(["git", "tag", tag_name, commit], cwd=repo_dir, check=True)


def get_remote_tag_push(repo_dir: str):
    proc = subprocess.run(
        ["git", "config", "get", "luxtest.remote.tag-push"], cwd=repo_dir, text=True, capture_output=True, check=False
    )
    return proc.stdout.strip() or DEFAULT_REMOTE_NAME


def get_tag_push_args(repo_dir: str, tag_name: str):
    remote = get_remote_tag_push(repo_dir)
    return ["git", "push", remote, tag_name]


###############################################################################
# Core functions
###############################################################################


def archive_web(name: str, push_tags=PushType.PRINT):
    now = datetime.datetime.now()
    date = now.strftime("%Y-%m-%d")

    # changing order here will change order hashes are placed in directory name
    repo_folders = {
        "luxtest": THIS_DIR,
        "usd": USD_REPO,
        "renders": luxtest_utils.get_renders_root(),
    }

    repo_hashes = {repo_name: get_git_hash(folder) for repo_name, folder in repo_folders.items()}
    dirname_pieces = [date, name]
    dirname_pieces.extend(f"{repo_name}-{hash}" for repo_name, hash in repo_hashes.items())
    dest_name = ".".join(dirname_pieces)
    rel_path = f"{WEB_ARCHIVE_DIRNAME}/{dest_name}"
    dest_path = os.path.join(THIS_DIR, rel_path)

    for repo_name, hash in repo_hashes.items():
        repo_folder = repo_folders[repo_name]
        # rel_path will also double as our tag name
        git_tag(repo_folder, rel_path, hash)

    print("moving:")
    print(f"  {WEB_DIR}")
    print("to:")
    print(f"  {dest_path}")

    shutil.move(WEB_DIR, dest_path)

    match push_tags:
        case PushType.PRINT:
            print()
            print("to push new tags:")
            for repo_folder in repo_folders.values():
                tag_push_args = get_tag_push_args(repo_folder, rel_path)
                tag_push_cmd = " ".join(shlex.quote(x) for x in tag_push_args)
                print(f"(cd '{repo_folder}' && {tag_push_cmd}')")
            print()
        case PushType.ON:
            for repo_folder in repo_folders.values():
                tag_push_args = get_tag_push_args(repo_folder, rel_path)
                subprocess.run(tag_push_args, check=False, cwd=repo_folder)
        case PushType.OFF:
            pass
        case _:
            raise ValueError("Invalid push_type: {push_type}")


###############################################################################
# CLI
###############################################################################


def get_parser():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("name", help="short descriptive tag to help identify this set of diffs")
    parser.add_argument(
        "--push-tags",
        nargs="?",
        type=str.lower,
        choices=tuple(x.name.lower() for x in PushType),
        default="print",
        const="yes",
    )
    return parser


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    parser = get_parser()
    args = parser.parse_args(argv)
    try:
        archive_web(name=args.name, push_tags=PushType.from_str(args.push_tags))
    except Exception:  # pylint: disable=broad-except

        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__" and not is_ipython():
    sys.exit(main())
