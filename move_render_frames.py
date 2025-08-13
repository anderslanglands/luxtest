#!/usr/bin/env python

"""Move render files from one frame range to another"""

import argparse
import dataclasses
import inspect
import os
import shutil
import subprocess
import sys
import traceback

from typing import Iterable, List, Optional, Tuple

###############################################################################
# Constants
###############################################################################

THIS_FILE = os.path.abspath(inspect.getsourcefile(lambda: None) or __file__)
THIS_DIR = os.path.dirname(THIS_FILE)

LUXTEST_REPO = THIS_DIR
RENDERS_REPO = os.path.join(THIS_DIR, "renders")


if THIS_DIR not in sys.path:
    sys.path.append(THIS_DIR)

import genLightParamDescriptions
import luxtest_const
import luxtest_utils

from luxtest_const import RENDERERS
from luxtest_utils import FrameRange

RENDER_ROOT = luxtest_utils.get_renders_root()
USE_GIT_BY_DEFAULT = os.path.isdir(os.path.join(RENDER_ROOT, ".git"))
RENDER_DIRS = luxtest_utils.get_render_dirs()

###############################################################################
# Utilities
###############################################################################


def is_ipython():
    try:
        __IPYTHON__  # type: ignore
    except NameError:
        return False
    return True


###############################################################################
# Core functions
###############################################################################


@dataclasses.dataclass
class RenameData:
    renderer: str
    light: str
    old_frame: int
    old_path: str
    new_frame: int
    new_path: str

    def summary_str(self):
        return f"{self.renderer} {self.light} light, {self.old_frame} to {self.new_frame}"

    def move(self):
        shutil.move(self.old_path, self.new_path)

    def git_move(self):
        subprocess.run(["git", "mv", self.old_path, self.new_path], cwd=RENDER_ROOT, check=True)


def move_frames(
    old_frames: FrameRange,
    new_frames: FrameRange,
    renderers: Optional[Iterable[str]] = None,
    lights: Iterable[str] = luxtest_const.DEFAULT_LIGHTS,
    dry_run: bool = False,
    git: bool = USE_GIT_BY_DEFAULT,
):
    if old_frames == new_frames:
        print("Frame range is unchanged - doing nothing")
        return
    # ensure renderers + lights are populated, and have uniform container type
    if renderers is None:
        renderers = RENDERERS
    renderers = tuple(renderers)
    lights = tuple(lights)

    print()
    print(f"Lights: {lights}")
    print(f"Renderers: {renderers}")
    print(f"Old Frames: {old_frames}")
    print(f"New Frames: {new_frames}")
    print()

    if old_frames.num_frames != new_frames.num_frames:
        raise ValueError("number of frames in new + old ranges must match")

    # gather list of all moves first
    renames: List[RenameData] = []
    for renderer in renderers:
        for light in lights:
            for old_frame, new_frame in zip(old_frames.iter_frames(), new_frames.iter_frames()):
                old_path, new_path = tuple(
                    luxtest_utils.get_image_path(light_name=light, renderer=renderer, frame=x, ext=".exr")
                    for x in (old_frame, new_frame)
                )
                if os.path.isfile(old_path):
                    renames.append(RenameData(renderer, light, old_frame, old_path, new_frame, new_path))

    # In order to reduce likelihood of name collision as we move frames, we change iteration order
    # depending on whether we're moving frames "up" or "down":
    # - if we're moving frames "up":
    #   - ie, from 1-20 to 11-30
    #   - then iterate from END to decrease odds of collision
    # - if we're moving frames "down":
    #   - ie, from 11-30 to 1-20
    #   - then iterate from START to decrease odds of collision
    if new_frames.end > old_frames.end:
        renames.reverse()

    # now that we've done that, "interior" collisions should be avoided (ie moving to a frame that was in the old range)
    # ...but can still have "exterior" collisons (when copying to a frame that wasn't in old range).

    # Validate this before starting...
    collisions = []
    for rename in renames:
        if old_frames.has_frame(rename.new_frame):
            # interior collsion, should be avoided when we set iteration order
            continue
        # check for possible exterior collision
        if os.path.isfile(rename.new_path):
            collisions.append(rename)

    if collisions:
        err_title = f"Cannot move frames - found {len(collisions)} collision(s)"
        err_msg = ""
        print(f"{err_title}:")
        for rename in collisions:
            frame_msg = f"  {rename.summary_str()} - path exists: {rename.new_path} "
            print(frame_msg)
            if not err_msg:
                err_msg = f"{err_title} - first: {frame_msg}"
        raise RuntimeError(err_msg)

    print("Moving:")
    for rename in renames:
        print()
        print(rename.old_path)
        print(rename.new_path)
        if not dry_run:
            if git:
                rename.git_move()
            else:
                rename.move()

    print()
    print(f"Finished moving {len(renames)} frames")
    if dry_run:
        print("  (DRY RUN - no frames actually moved)")


###############################################################################
# CLI
###############################################################################


def get_parser():
    all_light_names = genLightParamDescriptions.get_all_light_names()

    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "old_frames",
        type=FrameRange.from_str,
        help="Original frames that we wish to move; may be single digit, or inclusive range specified as start:end",
    )
    parser.add_argument(
        "new_frames",
        type=FrameRange.from_str,
        help=(
            "New frames that we wish to move our lights to; may be single digit, or inclusive range specified as"
            " start:end.  If the old_frames is a range, and the new_frames is a single digit, then "
            " the new_frames is assumed to be the new starting frame - ie, `1:10 21` is equivalent to `1:10 21:30`"
        ),
    )
    parser.add_argument(
        "-r",
        "--renderers",
        # We allow them to CHOOSE any existing render dir (RENDER_DIRS), but by default, only select known renderers
        # (RENDERERS)
        choices=RENDER_DIRS,
        metavar="RENDERER",
        nargs="+",
        help=(
            f"Only move images from the given renderer folder(s). Choices: {{{', '.join(RENDER_DIRS)}}}. If not"
            f" specified, render images for all known renderers: {RENDERERS}."
        ),
    )
    parser.add_argument(
        "-l",
        "--lights",
        choices=all_light_names,
        default=luxtest_const.DEFAULT_LIGHTS,
        metavar="LIGHT",
        nargs="+",
        help=(
            f"Only render images for the given light(s). Choices: {all_light_names}. If not specified,"
            " render images for default lights."
        ),
    )
    parser.add_argument(
        "-d",
        "--dry-run",
        action="store_true",
        help="Don't do actual renames - just print what would happen.",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "-g",
        "--git",
        default=USE_GIT_BY_DEFAULT,
        action="store_const",
        const=True,
        help=(
            "Use 'git mv' instead of a normal filesystem move. If not specified, will use 'git mv' if there is a"
            " renders/.git folder"
        ),
    )
    group.add_argument(
        "--no-git",
        dest="git",
        action="store_const",
        const=False,
        help=(
            "Always use a normal filesystem move, and not 'git mv'. If not specified, will use 'git mv' if there is a"
            " renders/.git folder"
        ),
    )
    return parser


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    parser = get_parser()
    args = parser.parse_args(argv)
    try:
        # If the old_frames is a range, and the new_frames is a single digit, then "
        # the new_frames is assumed to be the new starting frame - ie, `1:10 21` is equivalent to `1:10 21:30`

        # This is a CLI-only convenience, so handled here, not in move_frames()
        old_frames = args.old_frames
        new_frames = args.new_frames
        if old_frames.num_frames > 1 and new_frames.num_frames == 1:
            new_end = new_frames.start + old_frames.num_frames - 1
            new_frames = FrameRange(new_frames.start, new_end)
            assert old_frames.num_frames == new_frames.num_frames
        move_frames(
            old_frames=old_frames,
            new_frames=new_frames,
            renderers=args.renderers,
            lights=args.lights,
            dry_run=args.dry_run,
            git=args.git,
        )
    except Exception:  # pylint: disable=broad-except

        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__" and not is_ipython():
    sys.exit(main())
