#!/usr/bin/env python

"""Find and print the path to hython for the highest version
of houdini installed."""

import argparse
import os
import sys
import traceback

###############################################################################
# Core functions
###############################################################################


def ver_sort_key(version_str: str):
    return tuple((int(piece) if piece.isdigit() else piece) for piece in version_str.split("."))


def ver_install_pair_sort_key(version_install_pair: tuple[str, str]):
    version, install_path = version_install_pair
    return (ver_sort_key(version), install_path)


def find_hythons_windows() -> list[tuple[str, str]]:
    """Returns a list of tuples (version, hython_path)

    Sorted by version, ascending.

    Works by querying the windows registry
    """
    import winreg

    installations = []
    registry_paths = [
        r"SOFTWARE\Side Effects Software\Houdini",
        r"SOFTWARE\WOW6432Node\Side Effects Software\Houdini",
    ]

    for base_key in [winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE]:
        for path in registry_paths:
            try:
                with winreg.OpenKey(base_key, path) as key:
                    num_values = winreg.QueryInfoKey(key)[1]
                    for i in range(num_values):
                        val_name, val_value, _val_type = winreg.EnumValue(key, i)
                        name_split = val_name.split(".")
                        if len(name_split) >= 2 and all(x.isdigit() for x in name_split[:2]):
                            # val_name is a version
                            installations.append((val_name, os.path.join(val_value, "bin", "hython.exe")))
            except FileNotFoundError:
                continue
    installations.sort(key=ver_install_pair_sort_key)
    return installations


def find_hythons_linux() -> list[tuple[str, str]]:
    """Returns a list of tuples (version, hython_path)

    Sorted by version, ascending.

    Works by scanning /opt for hfs{version} directories
    """
    installations = []
    opt_dir = "/opt"

    if not os.path.isdir(opt_dir):
        return installations

    try:
        for entry in os.listdir(opt_dir):
            if entry.startswith("hfs") and len(entry) > 3:
                version_part = entry[3:]  # Remove "hfs" prefix

                # Check if version_part looks like a version (contains dots and digits)
                if "." in version_part and all(c.isdigit() or c == "." for c in version_part):
                    install_path = os.path.join(opt_dir, entry)
                    hython_path = os.path.join(install_path, "bin", "hython")

                    # Verify hython exists and is executable
                    if os.path.isfile(hython_path) and os.access(hython_path, os.X_OK):
                        installations.append((version_part, hython_path))
    except OSError:
        # Permission denied or other error reading /opt
        pass

    installations.sort(key=ver_install_pair_sort_key)
    return installations


def find_hythons() -> list[tuple[str, str]]:
    """Returns a list of tuples (version, hython_path)

    Sorted by version, ascending.
    """
    if sys.platform == "win32":
        return find_hythons_windows()
    elif sys.platform == "linux":
        return find_hythons_linux()

    # TODO: implement support for other platforms
    raise RuntimeError(f"Unsupported platform: {sys.platform}")


def print_houdini_bin_dir():
    print(find_hythons()[-1][1])


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
        print_houdini_bin_dir()
    except Exception:  # pylint: disable=broad-except

        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
