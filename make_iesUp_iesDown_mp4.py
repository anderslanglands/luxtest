# no hashbang - use .sh wrapper script

"""Create iesDown-karma.mp4, iesDown-ris.mp4, iesUp-karma.mp4, iesUp-ris.mp4"""

import argparse
import asyncio
import inspect
import os
import sys
import traceback

THIS_FILE = os.path.abspath(inspect.getsourcefile(lambda: None) or __file__)
THIS_DIR = os.path.dirname(THIS_FILE)

if THIS_DIR not in sys.path:
    sys.path.append(THIS_DIR)

import moviepy.video.io.ImageSequenceClip

import gendiffs
import genLightParamDescriptions
import luxtest_utils

from luxtest_utils import FrameRange

###############################################################################
# Constants
###############################################################################

FRAME_RANGES_BY_RENDERER = {
    "embree": FrameRange(99, 147),  # for bimodal formula renders
    "karma": FrameRange(50, 98),
    "ris": FrameRange(1, 49),
}

ALL_RENDERERS = tuple(FRAME_RANGES_BY_RENDERER)

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


def make_movies(fps: float = 24.0, renderers=ALL_RENDERERS):

    renders_root = luxtest_utils.get_renders_root()

    light_descriptions = genLightParamDescriptions.read_descriptions()

    for renderer in renderers:
        frame_range = FRAME_RANGES_BY_RENDERER[renderer]
        print()
        print("=" * 80)
        print(f"{renderer} - frames: {frame_range}")

        # first make sure we have the pngs
        # (we can't go straight from exrs, as moviepy can't handle color space conversion)
        asyncio.run(
            gendiffs.gen_images_async(
                light_descriptions,
                verbose=False,
                renders_root=renders_root,
                lights=["iesUp", "iesDown"],
                renderers=[renderer],
                frame_range=frame_range,
                do_diffs=False,
            )
        )

        for direction in ("Up", "Down"):
            light = f"ies{direction}"
            # Want to make a ping-pong - so do images forward first
            images = [
                luxtest_utils.get_image_path(light, renderer, f, ".png", renders_root=renders_root)
                for f in frame_range.iter_frames()
            ]
            # ...then reversed
            images.extend(reversed(images))
            clip = moviepy.video.io.ImageSequenceClip.ImageSequenceClip(images, fps=fps)
            output_file = os.path.join(renders_root, f"ies{direction}-{renderer}.mp4")
            clip.write_videofile(output_file)


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
        choices=ALL_RENDERERS,
        nargs="+",
        default=ALL_RENDERERS,
        help="Only render images for the given renderer(s); if not specified, render images for all renderers.",
    )
    return parser


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    parser = get_parser()
    args = parser.parse_args(argv)
    try:
        make_movies(renderers=args.renderers)
    except Exception:  # pylint: disable=broad-except

        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__" and not is_ipython():
    sys.exit(main())
