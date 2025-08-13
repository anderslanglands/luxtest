#!/bin/bash

set -e
set -u

THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

. "${THIS_DIR}/set_hou_env.bash"

"${LUXTEST_HYTHON}" "$@"
