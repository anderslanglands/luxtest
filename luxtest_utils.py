import inspect
import os
import subprocess
import sys

from typing import NamedTuple, Tuple

THIS_FILE = os.path.abspath(inspect.getsourcefile(lambda: None) or __file__)
THIS_DIR = os.path.dirname(THIS_FILE)

if THIS_DIR not in sys.path:
    sys.path.append(THIS_DIR)

import luxtest_const

###############################################################################
# Functions
###############################################################################


def try_decode(input_bytes):
    for codec in luxtest_const.CODEC_LIST:
        try:
            return input_bytes.decode(codec)
        except UnicodeDecodeError:
            pass
    return input_bytes


def get_renders_root() -> str:
    for test_path in luxtest_const.DEFAULT_RENDERS_ROOTS:
        if os.path.isdir(test_path):
            return test_path

    # couldn't find the renders path - clone it
    renders_root = luxtest_const.DEFAULT_RENDERS_ROOTS[0]
    # don't fetch all blobs for faster clone
    subprocess.run(["git", "clone", "--filter=blob:none", luxtest_const.DEFAULT_RENDERS_REPO_URL, renders_root])
    if not os.path.isdir(renders_root):
        raise RuntimeError(f"error cloning repo {luxtest_const.DEFAULT_RENDERS_REPO_URL!r} to {renders_root!r}")
    return renders_root


def get_render_dirs() -> Tuple[str, ...]:
    # filter out linux-hidden dirs (like ".git")
    return tuple(x.name for x in os.scandir(get_renders_root()) if x.is_dir() and not x.name.startswith("."))


def get_image_path(light_name, renderer: str, frame: int, ext: str, prefix="", renders_root=""):
    if not renders_root:
        renders_root = get_renders_root()
    ext = ext.lstrip(".")
    filename = f"{prefix}{light_name}-{renderer}.{frame:04}.{ext}"
    if ext == "png":
        base_dir = luxtest_const.WEB_IMG_ROOT
    elif ext == "exr":
        base_dir = os.path.join(renders_root, renderer)
    else:
        raise ValueError(f"unrecognized extension: {ext}")
    return os.path.join(base_dir, filename)


def get_image_url(light_name, renderer: str, frame: int, ext: str, prefix="", renders_root=""):
    if not renders_root:
        renders_root = get_renders_root()
    image_path = get_image_path(light_name, renderer, frame, ext, prefix=prefix, renders_root=renders_root)
    rel_path = os.path.relpath(image_path, luxtest_const.WEB_ROOT)
    return rel_path.replace(os.sep, "/")


###############################################################################
# Classes
###############################################################################


# Note: wanted to convert to a frozen dataclass, so we could have a more
# intuitive iter, which iterated over all frames in the range:
#
#  @dataclasses.dataclass(frozen=True)
#  class FrameRange:
#       ...
#
# ...but that made it serialize as a dict `{"start": 1, "end": 10}`` instead of
# a 2-item list `[1, 10]`.  No way to customize how dataclasses.asdict
# handles recursive serialization, so leaving as NamedTuple for now.
class FrameRange(NamedTuple):
    start: int
    end: int

    @property
    def num_frames(self):
        return self.end - self.start + 1

    def __str__(self):
        """Formatting suitable with usdrecord"""
        return f"{self.start}:{self.end}"

    def display_str(self):
        if len(self) == 1:
            return str(self.start)
        return f"{self.start}-{self.end}"

    def has_frame(self, frame: int) -> bool:
        return self.start <= frame <= self.end

    def issuperset(self, other: "FrameRange") -> bool:
        return self.start <= other.start and other.end <= self.end

    def issubset(self, other: "FrameRange") -> bool:
        return other.issuperset(self)

    @classmethod
    def from_str(cls, frames_str) -> "FrameRange":
        if ":" in frames_str:
            split = frames_str.split(":")
            if len(split) > 2:
                raise ValueError(
                    f"frames may only have a single ':', to denote start:end (inclusive) - got: {frames_str}"
                )
            frames = tuple(int(x) for x in split)
        else:
            frame = int(frames_str)
            frames = (frame, frame)
        return cls(*frames)

    def iter_frames(self):
        """Returns an iterator over every frame in the range

        As a tuple, an iterator is already defined, as (start, end); this
        is different from that, as it iterates over interior frames (and won't
        repeat start/end if they're the same)
        """
        return iter(range(self.start, self.end + 1))
