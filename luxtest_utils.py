import inspect
import os
import subprocess
import sys

THIS_FILE = os.path.abspath(inspect.getsourcefile(lambda: None) or __file__)
THIS_DIR = os.path.dirname(THIS_FILE)

if THIS_DIR not in sys.path:
    sys.path.append(THIS_DIR)

import luxtest_const


def try_decode(input_bytes):
    for codec in luxtest_const.CODEC_LIST:
        try:
            return input_bytes.decode(codec)
        except UnicodeDecodeError:
            pass
    return input_bytes


def get_renders_root():
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
