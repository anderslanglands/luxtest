#!/bin/bash

set -e
set -u

THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export LUXTEST_VENV_NAME=.venv

. "${THIS_DIR}/uv_install.sh"

if ! [ -f "${LUXTEST_VENV_ACTIVATE}" ]; then
    if [ -d "${UV_PROJECT_ENVIRONMENT}" ]; then
        # if the venv dir exists, but the activate script doesn't, assume it's a failed / incomplete venv
        rm -rf "${UV_PROJECT_ENVIRONMENT}"
    fi
    "${LUXTEST_UV_PATH}" --quiet venv --managed-python "${LUXTEST_VENV_NAME}"
fi

. "${LUXTEST_VENV_ACTIVATE}" &> /dev/null

"${LUXTEST_UV_PATH}" --quiet sync --group usd
