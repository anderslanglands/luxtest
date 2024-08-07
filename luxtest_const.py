import inspect
import locale
import os
import sys

THIS_FILE = os.path.abspath(inspect.getsourcefile(lambda: None) or __file__)
THIS_DIR = os.path.dirname(THIS_FILE)

###############################################################################
# Constants
###############################################################################

DEFAULT_OVERRIDES = {
    "inputs:shaping:cone:angle": 180,
}

DEFAULT_RENDERS_ROOTS = [
    os.path.join(THIS_DIR, "renders"),
    os.path.join(os.path.dirname(THIS_DIR), "luxtest_renders"),
]

DEFAULT_RENDERS_REPO_URL = "https://github.com/pmolodo/luxtest_renders.git"


def make_unique(*objs):
    return tuple(dict.fromkeys(x for x in objs if x is not None))


CODEC_LIST = make_unique(
    # list of codecs to try, in order...
    # use getattr because some stream wrappers (ie, houdinit's hou.ShellIO)
    # may not have a .encoding attr
    getattr(sys.stdout, "encoding", None),
    getattr(sys.stderr, "encoding", None),
    getattr(sys.stdin, "encoding", None),
    getattr(sys.__stdout__, "encoding", None),
    getattr(sys.__stderr__, "encoding", None),
    getattr(sys.__stdin__, "encoding", None),
    locale.getpreferredencoding(),
    "utf8",
)
