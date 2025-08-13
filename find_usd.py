#!/usr/bin/env python

"""Find and print the path to a USD installation."""

import argparse
import dataclasses
import json
import os
import re
import shutil
import sys
import traceback

from collections.abc import Iterable

###############################################################################
# Constants
###############################################################################

PXR_HEADER_SUBPATH = os.path.join("include", "pxr", "pxr.h")

# matches:
# define PXR_MAJOR_VERSION 0
# define PXR_MINOR_VERSION 25
# define PXR_PATCH_VERSION 5
PXR_VER_NAMES = ("MAJOR", "MINOR", "PATCH")
PXR_VERSION_DEF_RE = re.compile(
    rf"""^\s*#define\s+PXR_(?P<name>{'|'.join(PXR_VER_NAMES)})_VERSION\s+(?P<num>\d+)\s*$"""
)

PYTHON_DLL_RE = re.compile(r"^python(?P<major>[23])(?P<minor>\d{1,2})\.dll$")
PYTHON_SO_RE = re.compile(r"""^libpython(?P<major>[23])\.(?P<minor>\d{1,2})\.so(?:\.\d+)*$""")

###############################################################################
# Core functions
###############################################################################


@dataclasses.dataclass(order=True)
class USDInfo:
    root: str
    usd_version: str  # of MINOR.PATCH form, with PATCH 0-padded, ie, 25.02
    py_version: str  # of MAJOR.MINOR form, ie, 3.9; empty string if no python found


def get_usd_version(usd_install_root: str) -> str:
    pxr_h = os.path.join(usd_install_root, PXR_HEADER_SUBPATH)
    if not os.path.isdir(usd_install_root):
        raise ValueError(f"Invalid install root: {usd_install_root!r} - directory did not exist")
    if not os.path.isfile(pxr_h):
        raise ValueError(f"Invalid install root: {usd_install_root!r} - could not find: {PXR_HEADER_SUBPATH!r}")
    ver_nums: dict[str, int] = {}
    with open(pxr_h, encoding="utf8") as reader:
        for line in reader:
            match = PXR_VERSION_DEF_RE.match(line)
            if not match:
                continue
            name = match.group("name")
            if name not in PXR_VER_NAMES:
                raise RuntimeError(f"Error parsing {pxr_h!r} - found unexpection version define: PXR_{name}_VERSION")
            num = int(match.group("num"))
            if name in ver_nums:
                raise RuntimeError(
                    f"Error parsing {pxr_h!r} - found two values for PXR_{name}_VERSION: {ver_nums[name]!r} and {num}"
                )
            ver_nums[name] = num
            if len(ver_nums) == len(PXR_VER_NAMES):
                break
        else:
            missing_defs = [f"PXR_{name}_VERSION" for name in PXR_VER_NAMES if name not in ver_nums]
            raise RuntimeError(f"Error parsing {pxr_h!r} - unable to find: {missing_defs}")
    assert set(PXR_VER_NAMES) == set(ver_nums)
    assert ver_nums["MAJOR"] == 0
    assert len(ver_nums) == 3
    return f"{ver_nums["MINOR"]}.{ver_nums["PATCH"]:02}"


def _get_py_version_windows(usd_install_root: str) -> tuple[int, int] | None:
    pyd_path = os.path.join(usd_install_root, "lib", "python", "pxr", "Ar", "_ar.pyd")
    if not os.path.isfile(pyd_path):
        return None

    import pefile

    pe = pefile.PE(pyd_path)
    for linked_dll in pe.DIRECTORY_ENTRY_IMPORT:
        try:
            # if it's not ascii-compatible, it's not our python dll
            dll_name = linked_dll.dll.decode("ascii")
        except UnicodeDecodeError:
            continue
        match = PYTHON_DLL_RE.match(dll_name)
        if match:
            return tuple(int(match.group(x)) for x in ("major", "minor"))


def _get_py_version_linux(usd_install_root: str) -> tuple[int, int] | None:
    so_path = os.path.join(usd_install_root, "lib", "python", "pxr", "Ar", "_ar.so")
    if not os.path.isfile(so_path):
        return None

    from elftools.elf.elffile import ELFFile

    with open(so_path, "rb") as reader:
        elf = ELFFile(reader)
        dynamic = elf.get_section_by_name(".dynamic")
        if not dynamic:
            raise RuntimeError(f"python .so did not have a .dynamic section: {so_path!r}")
        for tag in dynamic.iter_tags():
            if tag.entry.d_tag != "DT_NEEDED":
                continue
            match = PYTHON_SO_RE.match(tag.needed)
            if match:
                return tuple(int(match.group(x)) for x in ("major", "minor"))


def get_py_version(usd_install_root: str) -> str:
    if sys.platform == "win32":
        ver_nums = _get_py_version_windows(usd_install_root)
    elif sys.platform == "linux":
        ver_nums = _get_py_version_linux(usd_install_root)
    else:
        raise RuntimeError(f"Unsupported os for get_py_version: {sys.platform}")
    if ver_nums is None:
        return ""
    assert len(ver_nums) == 2
    return ".".join(str(x) for x in ver_nums)


def _find_usd_env_var():
    return os.environ.get("LUXTEST_USD_ROOT", "")


def _find_usd_which_usdrecord():
    path = shutil.which("usdrecord")
    if not path:
        return ""
    return os.path.dirname(os.path.dirname(os.path.abspath(path)))


def find_usd() -> USDInfo | None:
    for generator in (_find_usd_env_var, _find_usd_which_usdrecord):
        path = generator()
        if not path:
            continue
        try:
            usd_ver = get_usd_version(path)
        except ValueError:
            continue
        py_ver = get_py_version(path)
        return USDInfo(root=path, usd_version=usd_ver, py_version=py_ver)


def print_usd_root_dir():
    usd_root = find_usd()
    if usd_root:
        data = dataclasses.asdict(usd_root)
        print(json.dumps(data))


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
    parser.parse_args(argv)
    try:
        print_usd_root_dir()
    except Exception:  # pylint: disable=broad-except

        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
