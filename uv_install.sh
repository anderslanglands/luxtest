#!/bin/bash

set -e
set -u

uname_s="$(uname -s)"

windows=0
case "${uname_s,,}" in
    linux*)     runtime=linux; os_type=$runtime;;
    darwin*)    runtime=mac; os_type=$runtime;;
    cygwin*)    runtime=cygwin; os_type=windows;;
    mingw*)     runtime=mingww; os_type=windows;;
    msys*)      runtime=msys; os_type=windows;;
    *)
        echo "unrecognized runtime/os: '${uname_s}'"
        exit 101
esac

export LUXTEST_OS_TYPE="${os_type}"
export LUXTEST_OS_RUNTIME="${runtime}"

THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -z "${UV_INSTALL_DIR-}" ]; then
    UV_INSTALL_DIR="${THIS_DIR}/.uv"
fi

if ! [ -d "$UV_INSTALL_DIR" ]; then
    mkdir -p $UV_INSTALL_DIR
fi

#make UV_INSTALL_DIR absolute
export UV_INSTALL_DIR="$(cd "$UV_INSTALL_DIR" && pwd)"

if [[ "${LUXTEST_OS_TYPE}" == "windows" ]]; then
    export LUXTEST_BIN_EXT=".exe"
    export LUXTEST_VENV_BIN_DIRNAME="Scripts"
    export LUXTEST_VENV_LIB_SUBDIR="Lib"
    if [ -z "${PATHSEP:-}" ]; then
        export PATHSEP=;
    fi
else
    export LUXTEST_BIN_EXT=""
    export LUXTEST_VENV_BIN_DIRNAME="bin"
    export LUXTEST_VENV_LIB_SUBDIR="lib/python"
    if [ -z "${PATHSEP:-}" ]; then
        export PATHSEP=:
    fi
fi

if [[ "${LUXTEST_OS_TYPE}" == "windows" ]]; then
    to_native_path()
    {
        # could use `cygpath -w`, but I'm not sure if we can assume that's available...
        "${THIS_DIR}/luxtest_python.sh" -c 'import pathlib, sys; print(pathlib.Path(sys.argv[1]))' "$1"
    }

    varname_to_native_path()
    {
        declare -n var_ref="$1"
        var_ref="$(to_native_path "${var_ref}")"
    }
else
    to_native_path()
    {
        echo "$1"
    }

    varname_to_native_path()
    {
        : # no-op
    }
fi

export UV_FILENAME="uv${LUXTEST_BIN_EXT}"

if [ -z "${LUXTEST_VENV_NAME:-}" ]; then
    export LUXTEST_VENV_NAME=".venv"
fi
export UV_PROJECT="${THIS_DIR}"
export UV_PROJECT_ENVIRONMENT="${THIS_DIR}/${LUXTEST_VENV_NAME}"
export LUXTEST_VENV_BIN_DIR="${UV_PROJECT_ENVIRONMENT}/${LUXTEST_VENV_BIN_DIRNAME}"
export LUXTEST_VENV_ACTIVATE="${LUXTEST_VENV_BIN_DIR}/activate"

# check if UV already installed
export LUXTEST_UV_PATH="${UV_INSTALL_DIR}/${UV_FILENAME}"
if [ -f "${LUXTEST_UV_PATH}" ]; then
    return 0
fi

# the uv install script uses XDG_BIN_HOME to tell it where to install
export XDG_BIN_HOME="${UV_INSTALL_DIR}"
export UV_NO_MODIFY_PATH=1
export INSTALLER_PRINT_QUIET=1

curl -LsSf https://astral.sh/uv/install.sh | sh
