#!/usr/bin/env python

"""Runs time trials"""

import argparse
import datetime
import inspect
import os
import subprocess
import sys
import traceback

from typing import Dict, Iterable, List, NamedTuple, Tuple

THIS_FILE = os.path.abspath(inspect.getsourcefile(lambda: None) or __file__)
THIS_DIR = os.path.dirname(THIS_FILE)

if THIS_DIR not in sys.path:
    sys.path.append(THIS_DIR)

import luxtest_utils

GEN_EMBREE = os.path.join(THIS_DIR, "genembree.py")
DEFAULT_TEST_USDA = os.path.join(THIS_DIR, "usd", "test", "embree_test_01.usda")
RENDERS_ROOT = luxtest_utils.get_renders_root()
DEFAULT_OUTPUT_DIR = os.path.join(RENDERS_ROOT, "test")

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


class FrameRange(NamedTuple):
    start: int
    end: int

    @property
    def num_frames(self):
        return self.end - self.start + 1

    def __str__(self):
        return f"{self.start}:{self.end}"


class TrialInfo(NamedTuple):
    frames: FrameRange
    num_runs: int


class TrialResult(NamedTuple):
    exitcode: int
    elapsed: datetime.timedelta
    args: List[str]


class Average(NamedTuple):
    average: float
    num: int

    @classmethod
    def from_total(cls, total, num):
        average = total / num
        return cls(average=average, num=num)

    def __str__(self):
        return f"Average: {self.average} (over {self.num} results)"


class Overhead(NamedTuple):
    overhead: float
    per_frame: float

    @classmethod
    def from_two_averages(cls, num_frames1: int, average1: float, num_frames2: int, average2: float):
        if num_frames1 == num_frames2:
            raise Exception("same num frames")

        per_frame = (average1 - average2) / (num_frames1 - num_frames2)
        overhead = average1 - num_frames1 * per_frame
        return cls(overhead=overhead, per_frame=per_frame)

    def __str__(self):
        return f"Overhead: {self.overhead} - Per-frame: {self.per_frame}"


def run_trial(frames: FrameRange):
    print()
    print("-" * 60)
    args = [sys.executable, GEN_EMBREE, "-f", str(frames), "-i", DEFAULT_TEST_USDA, "-o", DEFAULT_OUTPUT_DIR]
    print(to_shell_cmd(args))
    start = datetime.datetime.now()
    exitcode = subprocess.call(args)
    elapsed = datetime.datetime.now() - start
    return TrialResult(exitcode=exitcode, elapsed=elapsed, args=args)


def run_trials(trials: Iterable[TrialInfo], stop_on_error=True):
    # frames -> list of results
    results: Dict[FrameRange, TrialResult] = {}

    num_failures = 0
    num_successes = 0
    total_frames = 0

    start = datetime.datetime.now()
    for trial in trials:
        results_for_frame = results.setdefault(trial.frames, [])
        for i in range(trial.num_runs):
            result = run_trial(trial.frames)
            results_for_frame.append(result)
            total_frames += trial.frames.num_frames
            if result.exitcode:
                print("!" * 80)
                print(f"ERROR running trial - exitcode: {result.exitcode}")
                print("!" * 80)
                num_failures += 1
                if stop_on_error:
                    raise subprocess.CalledProcessError(result.exitcode, result.args, "", "")
            else:
                num_successes += 1
            print()
            print(f"Frames: {trial.frames} - Run {i + 1} / {trial.num_runs} - took: {result.elapsed}")
    elapsed = datetime.datetime.now() - start

    print(f"Ran {num_successes + num_failures} total renders, and {total_frames} total frames")
    print(f"Total elapsed time: {elapsed}")

    if not num_successes:
        print()
        print("!" * 80)
        print("!" * 80)
        print(f"No successful runs - had {num_failures} failures!")
        print("!" * 80)
        print("!" * 80)
        return

    print()
    print("=" * 80)
    print(f"Succesful runs: {num_successes} - Failures: {num_failures}")
    print()
    print_data(results)


def print_data(results: Dict[FrameRange, TrialResult]):
    if not results:
        print("No results - cannot print anything")
        return

    averages = {}
    for frames, trial_results in results.items():

        successes = [x for x in trial_results if x.exitcode == 0]
        if not successes:
            continue
        total_timedelta = sum((x.elapsed for x in successes), start=datetime.timedelta())
        total_seconds = total_timedelta.total_seconds()
        average = Average.from_total(total_seconds, len(successes))
        averages[frames] = average
        print(f"{tuple(frames)} - Avg: {average}")

    # want to estimate the how much startup overhead there is, and how much
    # per-frame time there is.  To do that, we need results for two FrameRanges,
    # with an unequal number of total frames.

    frame_range_set = set(averages)

    # want to find the frame ranges with the biggest having the greatest frame
    # range, with the first tiebreaker being number of successful results we
    # got for that range
    def sort_key(x: FrameRange):
        average = averages[x]
        return (x.num_frames, average.num, average.average, x.start)

    print()
    frame_range_list = sorted(frame_range_set, key=sort_key)

    # first will have the largest possible number of frames
    frange1 = frame_range_list.pop()
    different = [x for x in frame_range_list if x.num_frames != frange1.num_frames]
    if not different:
        # couldn't find two frame ranges with unequal num_frames... can't
        # estimate startup + per-frame time
        return
    frange2 = different[-1]
    overhead = Overhead.from_two_averages(
        frange1.num_frames,
        averages[frange1].average,
        frange2.num_frames,
        averages[frange2].average,
    )

    print(f"Estimated breakdown: {overhead}")
    print()


###############################################################################
# CLI
###############################################################################


def get_parser():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    return parser


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    parser = get_parser()
    args = parser.parse_args(argv)
    try:
        # hardcoding trials for now
        run_trials(
            # for testing:
            # [
            #     TrialInfo(frames=FrameRange(1, 1), num_runs=1),
            #     TrialInfo(frames=FrameRange(1, 2), num_runs=1),
            # ]
            # for farily quick results
            [
                TrialInfo(frames=FrameRange(1, 4), num_runs=5),
                TrialInfo(frames=FrameRange(1, 1), num_runs=5),
            ]
        )
    except Exception:  # pylint: disable=broad-except

        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__" and not is_ipython():
    sys.exit(main())
