#!/usr/bin/env python

"""CLI interface to does_something"""

import argparse
import inspect
import os
import re
import subprocess
import sys
import traceback

THIS_FILE = os.path.abspath(inspect.getsourcefile(lambda: None) or __file__)
THIS_DIR = os.path.dirname(THIS_FILE)

if THIS_DIR not in sys.path:
    sys.path.append(THIS_DIR)

import luxtest_utils

RENDERERS = ("embree", "arnold", "karma", "ris")

INPUT_NAME_RE = re.compile(r"""^iesTest-(?P<renderer>.*)\.(?P<camera>iesTop|iesBottom).(?P<frame>\d{4}).exr$""")
###############################################################################
# Utilities
###############################################################################


def is_ipython():
    try:
        __IPYTHON__  # type: ignore
    except NameError:
        return False
    return True


if sys.platform == "win32":
    to_shell_cmd = subprocess.list2cmdline
else:

    def to_shell_cmd(cmd_list):
        import shlex

        return " ".join(shlex.quote(x) for x in cmd_list)


###############################################################################
# Core functions
###############################################################################


def combine_ies_test_images(renderers=(), delete=True):
    to_delete = []
    if not renderers:
        renderers = RENDERERS
    renders_root = luxtest_utils.get_renders_root()
    for renderer in renderers:
        renderer_dir = os.path.join(renders_root, renderer)

        top_frames = {}
        bottom_frames = {}
        for entry in os.scandir(renderer_dir):
            if not entry.is_file():
                continue
            match = INPUT_NAME_RE.match(entry.name)
            if not match:
                continue
            frame_dict = {
                "iesTop": top_frames,
                "iesBottom": bottom_frames,
            }[match.group("camera")]
            if match.group("renderer") != renderer:
                raise RuntimeError(
                    f"found file {entry.path} with renderer {match.group('renderer')} in renderer dir {renderer_dir}"
                )
            frame = match.group("frame")
            frame_dict[frame] = entry

        top_set = set(top_frames)
        bottom_set = set(bottom_frames)

        top_only = top_set - bottom_set
        bottom_only = bottom_set - top_set

        mismatched = []
        mismatched.extend(top_frames[x] for x in top_only)
        mismatched.extend(bottom_frames[x] for x in bottom_only)
        if mismatched:
            print("WARNING: found mismatched frames without accompanying top or bottom frame:")
            print("=" * 80)
            for entry in mismatched:
                print(f"  {entry.path}")
            print()
        both = sorted(top_set.intersection(bottom_set))
        for frame in both:
            top_path = top_frames[frame].path
            bottom_path = bottom_frames[frame].path
            output_path = os.path.join(renderer_dir, f"iesTest-{renderer}.{frame}.exr")
            args = ["oiiotool", top_path, bottom_path, "--mosaic", "1x2", "-o", output_path]
            print(to_shell_cmd(args), flush=True)
            subprocess.check_call(args)
            print(f"Output: {output_path}")
            to_delete.append(top_path)
            to_delete.append(bottom_path)
    if delete:
        for path in to_delete:
            print(f"removing: {path}")
            os.remove(path)


###############################################################################
# CLI
###############################################################################


def get_parser():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-r",
        "--renderers",
        choices=RENDERERS,
        nargs="+",
        help="Only combine images for the given renderers; if not specified, combine images for all renderers.",
    )
    parser.add_argument(
        "-k", "--keep", action="store_true", help="Keep source half-image files after generating combined image"
    )
    return parser


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    parser = get_parser()
    args = parser.parse_args(argv)
    try:
        combine_ies_test_images(renderers=args.renderers, delete=not args.keep)
    except Exception:  # pylint: disable=broad-except
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__" and not is_ipython():
    sys.exit(main())
