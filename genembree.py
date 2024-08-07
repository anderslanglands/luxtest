#!/usr/bin/env python

"""Run the UsdLux_2 test suite"""

import argparse
import fnmatch
import inspect
import os
import re
import subprocess
import sys
import traceback

from glob import glob
from typing import Callable, Iterable, List, NamedTuple, Optional, Tuple

###############################################################################
# Constants
###############################################################################

THIS_FILE = os.path.abspath(inspect.getsourcefile(lambda: None) or __file__)
THIS_DIR = os.path.dirname(THIS_FILE)

if THIS_DIR not in sys.path:
    sys.path.append(THIS_DIR)

import combine_ies_test_images
import genLightParamDescriptions
import luxtest_utils
import pip_import

pip_import.pip_import("tqdm")

from tqdm import tqdm

from genLightParamDescriptions import FrameRange

EMBREE_DELEGATE = "Embree"
DEFAULT_DELEGATES = (EMBREE_DELEGATE,)
DEFAULT_INCLUDE_GLOBS = (os.path.join(THIS_DIR, "usd", "*.usda"),)
DEFAULT_EXCLUDE_GLOBS = ()
DEFAULT_OUTPUT_DIR = luxtest_utils.get_renders_root()
DEFAULT_RESOLUTION = 512
DEFAULT_CAMERAS = ("/cameras/camera1",)
DEFAULT_CAMERAS_BY_USD = {
    "iesTest": ("/cameras/iesTop", "/cameras/iesBottom"),
}

DEFAULT_SEED = 1

USD_RECORD_FRAME_RE = re.compile(rb"""^Recording time code: .*""")

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
# Dataclasses
###############################################################################


class UsdRecordCommand(NamedTuple):
    """Data needed for a single invocation of usdrecord"""

    name: str  # base name of the file - ie, the light name
    usd_path: str
    output_path: str
    renderer: str
    camera: str
    frames: FrameRange
    resolution: int
    samples: Optional[int]
    seed: int

    def render(self, frame_callback: Optional[Callable[[], None]] = None):
        return run_test(
            self.usd_path,
            self.output_path,
            delegate=self.renderer,
            resolution=self.resolution,
            samples=self.samples,
            camera=self.camera,
            frames=self.frames,
            seed=self.seed,
            frame_callback=frame_callback,
        )


###############################################################################
# Core functions
###############################################################################


def run_tests(
    include_globs: Iterable[str] = DEFAULT_INCLUDE_GLOBS,
    exclude_globs: Iterable[str] = DEFAULT_EXCLUDE_GLOBS,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    delegates: Iterable[str] = DEFAULT_DELEGATES,
    resolution: int = DEFAULT_RESOLUTION,
    samples: Optional[int] = None,
    cameras: Iterable[str] = (),
    frames: Optional[FrameRange] = None,
    seed: int = DEFAULT_SEED,
    progress_bar: bool = True,
) -> List[str]:
    """Runs tests on input usds matching given glob, for all given delegates

    Returns
    -------
    failures: List[UsdRecordCommand]
    """
    nullLight = genLightParamDescriptions.LightParamDescription.empty()

    light_descriptions = genLightParamDescriptions.read_descriptions()

    # strip empty globs, and convert iterables into tuples
    include_globs = tuple(x for x in include_globs if x)
    exclude_globs = tuple(x for x in exclude_globs if x)

    exclude_res = [re.compile(fnmatch.translate(x)) for x in exclude_globs]

    def is_excluded(path):
        return any(x.match(path) for x in exclude_res)

    if not include_globs:
        errmsg = (
            "ERROR: no input usd glob patterns specified. Please specify a glob pattern to match usd layers to render"
        )
        print(errmsg)
        return [errmsg]

    input_layers = []
    for pattern in include_globs:
        print(f"globbing: {pattern}")
        new_layers = []
        new_layers = [x for x in glob(pattern) if not is_excluded(x)]

        print(f"found {len(new_layers)} layers")
        for f in new_layers:
            print(f"  {f}")
        input_layers.extend(new_layers)

    if not input_layers:
        errmsg = f"ERROR: input glob patterns {include_globs} did not match any files"
        if exclude_res:
            errmsg += f", after excluding glob patterns {exclude_globs}"
        print(errmsg)
        return [errmsg]

    flat_list: List[UsdRecordCommand] = []
    total_frames = 0
    unique_cameras = set()

    for delegate in delegates:
        delegate_output_dir = os.path.join(output_dir, delegate.lower())
        os.makedirs(delegate_output_dir, exist_ok=True)

        for layer in input_layers:
            input_file = os.path.basename(layer)
            base = os.path.splitext(input_file)[0]

            if frames is None:
                test_frames = light_descriptions.get(base, nullLight).frames
            else:
                test_frames = frames

            if cameras:
                light_cameras = cameras
            else:
                light_cameras = DEFAULT_CAMERAS_BY_USD.get(base, DEFAULT_CAMERAS)
            unique_cameras.update(light_cameras)

            for camera in light_cameras:
                total_frames += test_frames.num_frames

                if len(light_cameras) > 1:
                    camera_filename_part = "." + os.path.basename(camera)
                else:
                    camera_filename_part = ""
                output_file = f"{base}-{delegate.lower()}{camera_filename_part}.####.exr"
                output_path = os.path.join(delegate_output_dir, output_file)

                flat_list.append(
                    UsdRecordCommand(
                        name=base,
                        usd_path=layer,
                        output_path=output_path,
                        renderer=delegate,
                        camera=camera,
                        frames=test_frames,
                        resolution=resolution,
                        samples=samples,
                        seed=seed,
                    )
                )

    num_commands = len(flat_list)
    print(f"Found: {len(delegates)} delegates - {len(input_layers)} files - {len(unique_cameras)} cameras ")
    print(f"Total usdrecord render commands: {num_commands} - Total frames: {total_frames}")
    print()

    if progress_bar:
        render_command_progress = tqdm(desc="Render commands", unit="command", total=num_commands, position=0)
        total_frames_progress = tqdm(desc="Total frames   ", unit="frame", total=total_frames, position=1)
        current_frames_progress = tqdm(desc="Command frames ", unit="frame", position=2)
    try:
        if progress_bar:

            def frame_progress_update():
                render_command_progress.refresh()
                total_frames_progress.update(1)
                current_frames_progress.update(1)

            frame_callback = frame_progress_update
        else:
            frame_callback = None

        failures = []
        for command in flat_list:
            if progress_bar:
                current_frames_progress.reset(total=command.frames.num_frames)
                current_frames_progress.clear()
            print()
            exitcode = command.render(frame_callback=frame_callback)
            if progress_bar:
                render_command_progress.update(1)
            if exitcode:
                failures.append(command)

            # auto-combine iesTest images if we did all cameras
            if command.name == "iesTest" and not cameras:
                print()
                print(f"Combining {base} images")
                combine_ies_test_images.combine_ies_test_images(renderers=["embree"])

        return failures
    finally:
        if progress_bar:
            render_command_progress.close()
            total_frames_progress.close()
            current_frames_progress.close()


def run_test(
    usd_path: str,
    output_path: str,
    delegate: str,
    resolution: int,
    samples: Optional[int],
    camera: str,
    frames: FrameRange,
    seed: int,
    frame_callback: Optional[Callable[[], None]] = None,
):

    usdrecord = "usdrecord"
    if sys.platform == "win32":
        usdrecord += ".cmd"

    cmd = [
        usdrecord,
        "--disableCameraLight",
        "--disableGpu",
        "--imageWidth",
        str(resolution),
        "--renderer",
        delegate,
        "--colorCorrectionMode=disabled",
    ]
    if frames is not None:
        cmd.extend(["--frames", str(frames)])
    if camera:
        cmd.extend(["--camera", camera])
    cmd.extend([usd_path, output_path])
    try:
        print(to_shell_cmd(cmd))
    except Exception:
        print(cmd)
        raise
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env["HDEMBREE_RANDOM_NUMBER_SEED"] = str(seed)
    if samples is not None:
        env["HDEMBREE_SAMPLES_TO_CONVERGENCE"] = str(samples)

    if frame_callback is None:
        # skip progress bar
        return subprocess.call(cmd, env=env)

    current_line = []

    # we watch for usdrecording lines like "Recording time code: 1.0000"
    # ...however, it prints these when it STARTS each frame, not when it finishes
    # we don't want to update progress each time we get this, as this would result
    # in a first frame "finish" time that would be very fast, and would skew
    # early time estimations.
    # So, instead we skip the frame_callback() the FIRST time we see this
    # message... and then add in one last frame_callback() when the process
    # finishes
    read_first_frame = False

    def process_finished_line(line):
        nonlocal read_first_frame
        match = USD_RECORD_FRAME_RE.match(line)
        if match and frame_callback is not None:
            if read_first_frame:
                frame_callback()
            else:
                read_first_frame = True
        else:
            print(luxtest_utils.try_decode(line))

    def process_text(newtext):
        if not newtext:
            return
        lines = newtext.split(b"\n")
        unfinished_line = lines.pop()
        for line in lines:
            line = line.rstrip(b"\r")
            if current_line:
                current_line.append(line)
                finished_line = b"".join(current_line)
                current_line.clear()
            else:
                finished_line = line
            process_finished_line(finished_line)
        if unfinished_line:
            current_line.append(unfinished_line)

    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE)
    while proc.poll() is None:
        newtext = proc.stdout.read1()
        process_text(newtext)

    # ok, proc finished, but we still might have text to read
    while True:
        newtext = proc.stdout.read1()
        if not newtext:
            break
        process_text(newtext)
    if frame_callback is not None:
        # callback for "finishing" the last frame
        frame_callback()

    if current_line:
        process_text(b"".join(current_line))
    return proc.returncode


###############################################################################
# CLI
###############################################################################


def get_parser():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-d",
        "--delegates",
        nargs="+",
        default=DEFAULT_DELEGATES,
        help=(
            "Delegates to use to render the test suite. Can specify multiple delegates, which will run each specified"
            " delegate sequentially."
        ),
    )
    parser.add_argument(
        "-r",
        "--resolution",
        type=int,
        default=DEFAULT_RESOLUTION,
        help="Resolution of the rendered test images",
    )
    parser.add_argument(
        "-s",
        "--samples",
        type=int,
        help=(
            "Number of samples per-pixel for the embree render delegate (if not specified, uses embree's default,"
            " currently 100)"
        ),
    )
    parser.add_argument(
        "-c",
        "--cameras",
        nargs="+",
        help="Prim paths to cameras to render from",
    )
    parser.add_argument(
        "-i",
        "--include",
        nargs="+",
        default=DEFAULT_INCLUDE_GLOBS,
        help="Glob pattern(s) to match input usd filepaths to render",
    )
    parser.add_argument(
        "-e",
        "--exclude",
        nargs="+",
        default=DEFAULT_EXCLUDE_GLOBS,
        help="Glob pattern(s) that will exclude usd filepaths to render - overrides a match against an include pattern",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=(
            "Base directory under which to write the rendered images. Subdirectories will be created for each render"
            " delegate."
        ),
    )
    parser.add_argument(
        "-f",
        "--frames",
        type=FrameRange.from_str,
        help=(
            "Only render the given frame or frame range; may be single digit, or inclusive range specified as start:end"
        ),
    )
    parser.add_argument(
        "-x",
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help="Set a random number seed, for repeatable results; set to -1 to use a different seed on each invocation",
    )
    parser.add_argument(
        "--no-progress-bar",
        dest="progress_bar",
        action="store_false",
        help="Disable the progress bar - may be useful for debugging",
    )

    return parser


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    parser = get_parser()
    args = parser.parse_args(argv)

    try:
        failures = run_tests(
            include_globs=args.include,
            exclude_globs=args.exclude,
            output_dir=args.output_dir,
            delegates=args.delegates,
            resolution=args.resolution,
            samples=args.samples,
            cameras=args.cameras,
            frames=args.frames,
            seed=args.seed,
            progress_bar=args.progress_bar,
        )
    except Exception:  # pylint: disable=broad-except
        traceback.print_exc()
        return 1

    print()
    if failures:
        print("!" * 80)
        print(f"Enountered {len(failures)} failures:")
        for f in failures:
            print(f)
        print("!" * 80)
        return 1
    print("All lights successfully rendered")
    return 0


if __name__ == "__main__" and not is_ipython():
    sys.exit(main())
