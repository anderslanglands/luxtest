# no hashbang - should be sourced!

set -e
set -u

THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! [[ -v "HTOA_STARTUP_LOG" ]]; then
    export HTOA_STARTUP_LOG=0
fi

# need to run find_hython.py - need python for that, so create / use
# the uv-managed venv
LUXTEST_HYTHON="$("${THIS_DIR}/luxtest_python.sh" "${THIS_DIR}/find_hython.py")"

export LUXTEST_VENV_NAME=.venv_houdini

. "${THIS_DIR}/uv_install.sh"

# Determine hython version

# Could use, ie, `hython -c "import sys; print(sys.version_info[:3])"``...
# ...but `hython -c` is VERY slow to startup (while `hython --version` is speedy)
hython_ver_str="$("${LUXTEST_HYTHON}" --version)"
if [[ "${hython_ver_str}" =~ (([0-9]+\.[0-9]+)\.[0-9]) ]]; then
    export LUXTEST_HYTHON_VER_3="${BASH_REMATCH[1]}"
    export LUXTEST_HYTHON_VER_2="${BASH_REMATCH[2]}"
else
    echo "Failed to determine hython python version: '$hython_ver_str'"
    exit 201
fi

verbosity="--quiet"
# verbosity="--verbose"


if [[ -f /etc/os-release ]] && grep -q "^ID=ubuntu" /etc/os-release; then
    UBUNTU=1
    # I'm getting a hard crash on quitting hython on Ubuntu - something in jemalloc segfaults when freeing the
    # houdini python module, if the RenderMan plugin has been loaded.

    # As a workaround, hard-exit on Ubuntu, with "os._exit(0)"
    NEED_HARD_EXIT=1
else
    UBUNTU=0
    NEED_HARD_EXIT=0
fi

if [ "${NEED_HARD_EXIT}" -eq 1 ]; then
    export PYTHONUSERBASE="${THIS_DIR}/python_user_dir_hard_exit"
    echo "Set PYTHONUSERBASE to ${PYTHONUSERBASE}"
fi

if ! [ -f "${LUXTEST_VENV_ACTIVATE}" ]; then
    if [ -d "${UV_PROJECT_ENVIRONMENT}" ]; then
        # if the venv dir exists, but the activate script doesn't, assume it's a failed / incomplete venv
        rm -rf "${UV_PROJECT_ENVIRONMENT}"
    fi

    # If we just do: "uv venv --python $LUXTEST_HYTHON", uv errors because it
    # tries to query information using `hython -I`, and hython doesn't work with -I

    # Instead, try to get the "true" python binary, not the hython wrapper...
    LUXTEST_PYTHON_BASE_PREFIX="$("${LUXTEST_HYTHON}" -c 'import sys; print(sys.base_prefix)')"
    if [ "${LUXTEST_OS_TYPE}" == "windows" ]; then
        LUXTEST_PYTHON_BIN="${LUXTEST_PYTHON_BASE_PREFIX}/python.exe"
    else
        LUXTEST_PYTHON_BIN="${LUXTEST_PYTHON_BASE_PREFIX}/bin/python"
    fi
    "${LUXTEST_UV_PATH}" ${verbosity} venv --python "${LUXTEST_PYTHON_BIN}" "${UV_PROJECT_ENVIRONMENT}"
fi

"${LUXTEST_UV_PATH}" ${verbosity} sync

if [ "${LUXTEST_OS_TYPE}" == "windows" ]; then
    export LUXTEST_VENV_PYLIB_SUBDIR="Lib"
else
    export LUXTEST_VENV_PYLIB_SUBDIR="lib/python${LUXTEST_HYTHON_VER_2}"
fi
export LUXTEST_VENV_SITE_PACKAGES_DIR="${UV_PROJECT_ENVIRONMENT}/${LUXTEST_VENV_PYLIB_SUBDIR}/site-packages"

varname_to_native_path LUXTEST_VENV_BIN_DIR
varname_to_native_path LUXTEST_VENV_SITE_PACKAGES_DIR

export PATH="${LUXTEST_VENV_BIN_DIR}${PATH:+:${PATH}}"
export PYTHONPATH="${LUXTEST_VENV_SITE_PACKAGES_DIR}${PYTHONPATH:+${PATHSEP}${PYTHONPATH}}"

# prevent HTOA from spamming on houdini startup, if it's installed
export HTOA_STARTUP_LOG="${HTOA_STARTUP_LOG:-0}"