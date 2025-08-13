#!/bin/bash

set -e
set -u

THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
THIS_FILENAME="$(basename "${BASH_SOURCE[0]}")"
THIS_BASE_FILENAME="${THIS_FILENAME%.*}"

"${THIS_DIR}/luxtest_python.sh" "${THIS_DIR}/${THIS_BASE_FILENAME}.py" "$@"