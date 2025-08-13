# no hashbang - should be sourced!

set -e
set -u

THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# need to run find_usd.py - need python for that, so create / use
# the uv-managed venv
LUXTEST_USD_INFO="$("${THIS_DIR}/luxtest_python.sh" "${THIS_DIR}/find_usd.py")"

if [ -z "${LUXTEST_USD_INFO}" ]; then
    echo "Unable to find a USD installation"
    echo "You must do one of the following:"
    echo "  - set the LUXTEST_USD_ROOT environment variable"
    echo "  - add the bin folder (which must have usdrecord) onto your PATH"
    exit 201
fi

get_json_field()
{
    # ie:
    #    get_json_field foo '{"foo": 6, "bar": 2}'
    #    6
    "${THIS_DIR}/luxtest_python.sh" -c '
import json
import sys
name = sys.argv[1]
json_data = sys.argv[2]
data = json.loads(json_data)
print(data[name])' "$1" "$2"
}

export LUXTEST_USD_VER="$(get_json_field usd_version "${LUXTEST_USD_INFO}")"
export LUXTEST_PY_VER="$(get_json_field py_version "${LUXTEST_USD_INFO}")"
export LUXTEST_USD_ROOT="$(get_json_field root "${LUXTEST_USD_INFO}")"

export LUXTEST_VENV_NAME=.venv_usdlux2
. "${THIS_DIR}/uv_install.sh"

if ! [ -f "${LUXTEST_VENV_ACTIVATE}" ]; then
    if [ -d "${UV_PROJECT_ENVIRONMENT}" ]; then
        # if the venv dir exists, but the activate script doesn't, assume it's a failed / incomplete venv
        rm -rf "${UV_PROJECT_ENVIRONMENT}"
    fi
    "${LUXTEST_UV_PATH}" --quiet venv --managed-python --python "${LUXTEST_PY_VER}" "${LUXTEST_VENV_NAME}"
fi

. "${LUXTEST_VENV_ACTIVATE}" &> /dev/null

"${LUXTEST_UV_PATH}" --quiet sync

# now add in usd paths

export LUXTEST_USD_BIN_DIR="${LUXTEST_USD_ROOT}/bin"
export LUXTEST_USD_LIB_DIR="${LUXTEST_USD_ROOT}/lib"
export LUXTEST_USD_LIB_PYTHON_DIR="${LUXTEST_USD_LIB_DIR}/python"
export LUXTEST_PLUGIN_DIR="${LUXTEST_USD_ROOT}/plugin/usd"

varname_to_native_path LUXTEST_USD_ROOT
varname_to_native_path LUXTEST_USD_BIN_DIR
varname_to_native_path LUXTEST_USD_LIB_DIR
varname_to_native_path LUXTEST_USD_LIB_PYTHON_DIR
varname_to_native_path LUXTEST_PLUGIN_DIR

export PATH="${LUXTEST_USD_BIN_DIR}${PATH:+:${PATH}}"
export PYTHONPATH="${LUXTEST_USD_LIB_PYTHON_DIR}${PYTHONPATH:+${PATHSEP}${PYTHONPATH}}"
if [[ "${LUXTEST_OS_TYPE}" == "windows" ]]; then
    export PATH="${LUXTEST_USD_LIB_DIR}:${LUXTEST_PLUGIN_DIR}${PATH:+:${PATH}}"
else
    export LD_LIBRARY_PATH="${LUXTEST_USD_LIB_DIR}:${LUXTEST_PLUGIN_DIR}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
fi