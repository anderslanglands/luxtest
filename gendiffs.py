# no hashbang - use .sh wrapper script

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
import sysconfig
import textwrap
import traceback

from typing import Dict, Iterable, Optional

import tqdm.asyncio

###############################################################################
# Constants
###############################################################################

THIS_FILE = os.path.abspath(inspect.getsourcefile(lambda: None) or __file__)
THIS_DIR = os.path.dirname(THIS_FILE)

if THIS_DIR not in sys.path:
    sys.path.append(THIS_DIR)

import genLightParamDescriptions
import luxtest_const
import luxtest_utils

from luxtest_utils import FrameRange, get_image_path, get_image_url

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

NUM_CPUS = multiprocessing.cpu_count()

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


async def run(args: Iterable[str], check=False, verbose=False, **kwargs):
    if verbose:
        print(f"Running: {to_shell_cmd(args)}")
    proc = await asyncio.create_subprocess_exec(
        args[0], *args[1:], stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs
    )
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


def _calc_oiiotool_path() -> str:
    oiiotool = os.environ.get("LUXTEST_OIIOTOOL")
    if oiiotool:
        return oiiotool
    oiiotool = shutil.which("oiiotool")
    if oiiotool:
        return oiiotool
    scripts_dir = sysconfig.get_path("scripts")
    new_path = f"{scripts_dir}{os.pathsep}{os.environ['PATH']}"
    oiiotool = shutil.which("oiiotool", path=new_path)
    if oiiotool:
        return oiiotool
    raise RuntimeError("Could not find path to oiiotool")


OIIOTOOL = _calc_oiiotool_path()


async def run_oiiotool(args, verbose=False, **kwargs):
    cmd = [OIIOTOOL] + list(args)
    # houdini / hython sets PYTHONHOME, which messes oiiotool up
    env = kwargs.pop("env", None) or dict(os.environ)
    env.pop("PYTHONHOME", "")
    return await run(cmd, verbose=verbose, env=env, **kwargs)


###############################################################################
# Core functions
###############################################################################


async def update_png(exr_path, png_path, verbose=False):

    if needs_update(exr_path, png_path):
        if verbose:
            print(f"Creating png: {png_path}")
        cmd = [
            exr_path,
            "--ch",
            "R,G,B",
            "--colorconvert",
            "linear",
            "sRGB",
            "-o",
            png_path,
        ]
        proc = await run_oiiotool(cmd, verbose=verbose, check=True)
        if not os.path.isfile:
            print(f"Error - output png did not exist: {png_path}")
            raise_proc_error(proc, verbose)


async def update_diff(exr_path1, exr_path2, diff_path, verbose=False):
    cmd = [
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
    proc = await run_oiiotool(cmd, verbose=verbose)
    if not os.path.isfile:
        print(f"Error - output diff png did not exist: {diff_path}")
        raise_proc_error(proc, verbose)


async def gen_images_async(
    light_descriptions,
    verbose=False,
    max_concurrency=-1,
    renders_root="",
    do_diffs=True,
    lights: Optional[Iterable[str]] = None,
    renderers: Iterable[str] = luxtest_const.RENDERERS,
    frame_range: Optional[FrameRange] = None,
):
    all_tasks = []
    num_possible_images = 0

    renderers = list(renderers)
    if lights is not None:
        lights = list(lights)

    flat_frames = []
    for name, description in light_descriptions.items():
        if lights is not None and name not in lights:
            continue
        if frame_range is not None:
            light_frame_range = frame_range
        else:
            light_frame_range = description.frames
        for frame in light_frame_range.iter_frames():
            flat_frames.append((name, description, frame))

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

        if do_diffs:
            embree_exr_path = get_image_path(name, "embree", frame, "exr", renders_root=renders_root)

        for renderer in renderers:
            renderer_exr_path = get_image_path(name, renderer, frame, "exr", renders_root=renders_root)
            renderer_png_path = get_image_path(name, renderer, frame, "png", renders_root=renders_root)
            queue_png_update(renderer_exr_path, renderer_png_path)

            # don't need to do a diff of embree with itself!
            if renderer == "embree":
                continue

            if do_diffs:
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
    num_cols = len(luxtest_const.THIRD_PARTY_RENDERERS) * 2 + 1

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
        for renderer in luxtest_const.THIRD_PARTY_RENDERERS:
            html += textwrap.dedent(
                f"""
                    <td>{renderer}</td>
                    <td>{renderer} diff</td>
                """
            )

        html += "\n</tr>"
        for frame in description.frames.iter_frames():

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

            for renderer in luxtest_const.THIRD_PARTY_RENDERERS:
                renderer_url = get_image_url(name, renderer, frame, "png", renders_root=renders_root)
                diff_url = get_image_url(name, renderer, frame, "png", prefix="diff-", renders_root=renders_root)

                html += f'    <td><img src="{renderer_url}"</td>\n'
                html += f'    <td><img src="{diff_url}"</td>\n'

            html += "  </tr>"

        html += "</table>\n"
    html += HTML_END

    with open(os.path.join(luxtest_const.WEB_ROOT, "luxtest.html"), "w", encoding="utf8", newline="\n") as f:
        f.write(html)

    shutil.copyfile("luxtest.css", os.path.join(luxtest_const.WEB_ROOT, "luxtest.css"))


def gen_diffs(verbose=False, max_concurrency=-1, lights: Iterable[str] = luxtest_const.DEFAULT_LIGHTS):
    start = datetime.datetime.now()
    lights = tuple(lights)  # in case it's an iterable
    light_descriptions = genLightParamDescriptions.read_descriptions()
    light_descriptions = {light: desc for light, desc in light_descriptions.items() if light not in SKIP_LIGHTS}
    if lights:
        light_descriptions = {light: desc for light, desc in light_descriptions.items() if light in lights}

    renders_root = luxtest_utils.get_renders_root()
    os.makedirs(luxtest_const.WEB_IMG_ROOT, exist_ok=True)
    gen_images(light_descriptions, verbose=verbose, max_concurrency=max_concurrency, renders_root=renders_root)
    gen_html(light_descriptions, renders_root=renders_root)
    elapsed = datetime.datetime.now() - start
    print(f"Done generating diffs - took: {elapsed}")


###############################################################################
# CLI
###############################################################################


def get_parser():
    all_light_names = genLightParamDescriptions.get_all_light_names()

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
        "--lights",
        metavar="LIGHT",
        choices=all_light_names,
        nargs="+",
        default=luxtest_const.DEFAULT_LIGHTS,
        help=(
            f"Only render images for the given light(s).  Choices: {all_light_names}.  If not specified, render"
            " images for the set of default lights."
        ),
    )
    return parser


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    parser = get_parser()
    args = parser.parse_args(argv)
    try:
        gen_diffs(verbose=args.verbose, max_concurrency=args.j, lights=args.lights)
    except Exception:  # pylint: disable=broad-except

        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__" and not is_ipython():
    sys.exit(main())
