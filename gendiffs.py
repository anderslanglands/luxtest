#!/usr/bin/env python


"""Generate a web page showing UsdLux image diffs

...between the reference embree implementation and other renderers (ie, arnold,
karma, and RenderMan RIS)
"""


import argparse
import asyncio
import datetime
import inspect
import multiprocessing
import os
import shutil
import subprocess
import sys
import textwrap
import traceback

from typing import Dict, Iterable

###############################################################################
# Constants
###############################################################################

THIS_FILE = os.path.abspath(inspect.getsourcefile(lambda: None) or __file__)
THIS_DIR = os.path.dirname(THIS_FILE)

if THIS_DIR not in sys.path:
    sys.path.append(THIS_DIR)

import genLightParamDescriptions
import luxtest_utils
import pip_import

pip_import.pip_import("tqdm")
import tqdm.asyncio

WEB_DIR_NAME = "web"
WEB_ROOT = os.path.join(THIS_DIR, WEB_DIR_NAME)
WEB_IMG_ROOT = os.path.join(WEB_ROOT, "img")

RENDERERS = [
    "karma",
    "ris",
    "arnold",
]

OUTPUT_DIR = "diff"

MAP = "magma"

HTML_START = """<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>UsdLux Comparison</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="description" content="Comparison of hydra delegates to hdEmbree UsdLux reference">
    <link rel="stylesheet" href="luxtest.css">
  </head>
  <body>

    <div class="wrapper">
      <div class="navbar">
"""

HTML_NAVBAR_END = """\
      </div> <!-- navbar -->
      <div class="main">
"""

HTML_END = """<!DOCTYPE html>
      </div> <!-- main -->
    </div> <!-- wrapper -->
  </body>
"""

OIIOTOOL = os.environ.get("LUXTEST_OIIOTOOL", "oiiotool")

NUM_CPUS = multiprocessing.cpu_count()

# if we can't read light_descriptions, use this
FALLBACK_LIGHTS = (
    "cylinder",
    "disk",
    "distant",
    "dome",
    "rect",
    "sphere",
    "visibleRect",
)

SKIP_LIGHTS = ("ies_scale",)


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


def normalize_concurrency(concurrency: int):
    if concurrency <= 0:
        concurrency += NUM_CPUS
    return max(concurrency, 1)


def needs_update(existing, dependent):
    if os.path.exists(dependent):
        return os.path.getmtime(existing) > os.path.getmtime(dependent)
    return True


def iter_frames(light_description):
    start, end = light_description.frames
    return range(start, end + 1)


def get_image_path(light_name, renderer: str, frame: int, ext: str, prefix="", renders_root=""):
    if not renders_root:
        renders_root = luxtest_utils.get_renders_root()
    ext = ext.lstrip(".")
    filename = f"{prefix}{light_name}-{renderer}.{frame:04}.{ext}"
    if ext == "png":
        base_dir = WEB_IMG_ROOT
    elif ext == "exr":
        base_dir = os.path.join(renders_root, renderer)
    else:
        raise ValueError(f"unrecognized extension: {ext}")
    return os.path.join(base_dir, filename)


def get_image_url(light_name, renderer: str, frame: int, ext: str, prefix="", renders_root=""):
    if not renders_root:
        renders_root = luxtest_utils.get_renders_root()
    image_path = get_image_path(light_name, renderer, frame, ext, prefix=prefix, renders_root=renders_root)
    rel_path = os.path.relpath(image_path, WEB_ROOT)
    return rel_path.replace(os.sep, "/")


def print_streams(proc: subprocess.CompletedProcess):
    for stream_name in ("stdout", "stderr"):
        stream = getattr(proc, stream_name, None)
        print("=" * 80)
        print(f"{stream_name}:")
        print()
        print(luxtest_utils.try_decode(stream))


def raise_proc_error(proc: subprocess.CompletedProcess, verbose: bool):
    print()
    if not verbose:
        # if not verbose, we haven't printed output yet - do so now
        print_streams(proc)
    print("=" * 80)
    print("Error running commmand:")
    print(to_shell_cmd(proc.args))
    print(f"Exitcode: {proc.returncode}")
    print("=" * 80)
    raise subprocess.CalledProcessError(proc.returncode, proc.args, proc.stdout, proc.stderr)


async def run(args: Iterable[str], check=False, verbose=False):
    if verbose:
        print(f"Running: {to_shell_cmd(args)}")
    proc = await asyncio.create_subprocess_exec(args[0], *args[1:], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = await proc.communicate()
    completed_proc = subprocess.CompletedProcess(args=args, returncode=proc.returncode, stdout=stdout, stderr=stderr)
    if verbose:
        print_streams(completed_proc)
        print("=" * 80)
    if completed_proc.returncode:
        if check:
            raise_proc_error(completed_proc, verbose)
        if verbose:
            print(f"Exitcode: {completed_proc.returncode}")
    return completed_proc


###############################################################################
# Core functions
###############################################################################


async def update_png(exr_path, png_path, verbose=False):

    if needs_update(exr_path, png_path):
        if verbose:
            print(f"Creating png: {png_path}")
        cmd = [
            OIIOTOOL,
            exr_path,
            "--ch",
            "R,G,B",
            "--colorconvert",
            "linear",
            "sRGB",
            "-o",
            png_path,
        ]
        proc = await run(cmd, verbose=verbose, check=True)
        if not os.path.isfile:
            print(f"Error - output png did not exist: {png_path}")
            raise_proc_error(proc, verbose)


async def update_diff(exr_path1, exr_path2, diff_path, verbose=False):
    cmd = [
        OIIOTOOL,
        exr_path1,
        exr_path2,
        "--diff",
        "--absdiff",
        "--mulc",
        "2,2,2,1",
        "--colormap",
        MAP,
        "--colorconvert",
        "linear",
        "sRGB",
        "-o",
        diff_path,
    ]
    proc = await run(cmd, verbose=verbose)
    if not os.path.isfile:
        print(f"Error - output diff png did not exist: {diff_path}")
        raise_proc_error(proc, verbose)


async def gen_images_async(light_descriptions, verbose=False, max_concurrency=-1, renders_root=""):
    flat_frames = []
    for name, description in light_descriptions.items():
        for frame in iter_frames(description):
            flat_frames.append((name, description, frame))

    all_tasks = []
    num_possible_images = 0

    def queue_png_update(exr_path, png_path):
        nonlocal num_possible_images
        num_possible_images += 1
        if needs_update(exr_path, png_path):
            all_tasks.append(update_png(exr_path, png_path, verbose=verbose))

    def queue_diff_update(exr_path1, exr_path2, diff_path):
        nonlocal num_possible_images
        num_possible_images += 1
        if needs_update(exr_path1, diff_path) or needs_update(exr_path2, diff_path):
            all_tasks.append(update_diff(exr_path1, exr_path2, diff_path, verbose=verbose))

    print("Finding how many images need to be updated:")
    progress = tqdm.tqdm(flat_frames)
    for name, description, frame in progress:
        progress.set_postfix({"name": name, "frame": frame})
        embree_exr_path = get_image_path(name, "embree", frame, "exr", renders_root=renders_root)
        embree_png_path = get_image_path(name, "embree", frame, "png", renders_root=renders_root)
        queue_png_update(embree_exr_path, embree_png_path)

        for renderer in RENDERERS:
            renderer_exr_path = get_image_path(name, renderer, frame, "exr", renders_root=renders_root)
            renderer_png_path = get_image_path(name, renderer, frame, "png", renders_root=renders_root)
            queue_png_update(renderer_exr_path, renderer_png_path)

            diff_png_path = get_image_path(name, renderer, frame, "png", prefix="diff-", renders_root=renders_root)
            queue_diff_update(embree_exr_path, renderer_exr_path, diff_png_path)

    print(f"Generating {len(all_tasks)} images (out of possible {num_possible_images}):")

    # dont' want to overwhelm system by launching too many subprocess
    max_concurrency = normalize_concurrency(max_concurrency)
    proc_limiter = asyncio.Semaphore(max_concurrency)

    async def proc_limited_coroutine(coroutine):
        async with proc_limiter:
            return await coroutine

    limited_tasks = [proc_limited_coroutine(x) for x in all_tasks]

    await tqdm.asyncio.tqdm_asyncio.gather(*limited_tasks)


def gen_images(light_descriptions, verbose=False, max_concurrency=-1, renders_root=""):
    asyncio.run(
        gen_images_async(light_descriptions, verbose, max_concurrency=max_concurrency, renders_root=renders_root)
    )


def gen_html(light_descriptions: Dict[str, genLightParamDescriptions.LightParamDescription], renders_root=""):
    html = HTML_START
    num_cols = len(RENDERERS) * 2 + 1

    # sort first by number of frames (so tests with, ie, only one frame appear at top and are easy to find), then
    # alphabetically
    def sort_key(name_desc_pair):
        name, description = name_desc_pair
        return (description.frames.num_frames, description.frames.start, name)

    sorted_lights = sorted(light_descriptions.items(), key=sort_key)

    for name, description in sorted_lights:
        # add navbar links first
        html += f"""<p><a href="#{name}">{name}</a></p>"""

    html += HTML_NAVBAR_END

    for name, description in sorted_lights:
        # now add main body
        summaries_by_start_frame = genLightParamDescriptions.get_light_group_summaries(name, description)

        html += textwrap.dedent(
            f"""<h1 id="{name}">{name}</h1>

            <table>
            <tr>
                <td>Frame</td>
                <td>Ref</td>
            """
        )
        for renderer in RENDERERS:
            html += textwrap.dedent(
                f"""
                    <td>{renderer}</td>
                    <td>{renderer} diff</td>
                """
            )

        html += "\n</tr>"
        for frame in iter_frames(description):

            if frame in summaries_by_start_frame:
                desc = summaries_by_start_frame[frame]
                html += "  <tr></tr>\n"
                html += "  <tr>\n"
                html += f"    <td></td><td colspan='{num_cols}'><em>{desc}</em></td>\n"
                html += "  </tr>\n"

            html += "  <tr>\n"
            html += f"    <td>{frame:04}</td>"

            embree_url = get_image_url(name, "embree", frame, "png", renders_root=renders_root)

            html += f'    <td><img src="{embree_url}"</td>\n'

            for renderer in RENDERERS:
                renderer_url = get_image_url(name, renderer, frame, "png", renders_root=renders_root)
                diff_url = get_image_url(name, renderer, frame, "png", prefix="diff-", renders_root=renders_root)

                html += f'    <td><img src="{renderer_url}"</td>\n'
                html += f'    <td><img src="{diff_url}"</td>\n'

            html += "  </tr>"

        html += "</table>\n"
    html += HTML_END

    with open(os.path.join(WEB_ROOT, "luxtest.html"), "w", encoding="utf8") as f:
        f.write(html)

    shutil.copyfile("luxtest.css", os.path.join(WEB_ROOT, "luxtest.css"))


def gen_diffs(verbose=False, max_concurrency=-1, lights: Iterable[str] = ()):
    start = datetime.datetime.now()
    lights = tuple(lights)  # in case it's an iterable
    light_descriptions = genLightParamDescriptions.read_descriptions()
    light_descriptions = {light: desc for light, desc in light_descriptions.items() if light not in SKIP_LIGHTS}
    if lights:
        light_descriptions = {light: desc for light, desc in light_descriptions.items() if light in lights}

    renders_root = luxtest_utils.get_renders_root()
    os.makedirs(WEB_IMG_ROOT, exist_ok=True)
    gen_images(light_descriptions, verbose=verbose, max_concurrency=max_concurrency, renders_root=renders_root)
    gen_html(light_descriptions, renders_root=renders_root)
    elapsed = datetime.datetime.now() - start
    print(f"Done generating diffs - took: {elapsed}")


###############################################################################
# CLI
###############################################################################


def get_parser():
    try:
        light_descriptions = genLightParamDescriptions.read_descriptions()
        light_names = sorted(light_descriptions)
    except Exception as err:
        print("Error reading light names from light_descriptions.json:")
        print(err)
        print("...using fallback light names")
        light_names = FALLBACK_LIGHTS

    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument(
        "-j",
        type=int,
        default="-1",
        help=(
            "Number of oiiotool procs to run in parallel; 0 means use multiprocessing.cpu_count(); negative values are"
            " subtracted from multiprocessing.cpu_count()"
        ),
    )
    parser.add_argument(
        "-l",
        "--light",
        choices=light_names,
        action="append",
        dest="lights",
        help=(
            "Only render images for the given lights; if not specified, render images for all lights. May be repeated."
        ),
    )
    return parser


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    parser = get_parser()
    args = parser.parse_args(argv)
    try:
        gen_diffs(verbose=args.verbose, max_concurrency=args.j, lights=args.lights or ())
    except Exception:  # pylint: disable=broad-except

        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__" and not is_ipython():
    sys.exit(main())
