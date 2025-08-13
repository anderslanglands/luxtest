#!/bin/bash

set -e
set -u

THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

./genembree.sh -i usd/iesLibPreview.usda -f 12:20 -s 8000
./genembree.sh -i usd/iesTest.usda -f 12:20 -s 8000
./genembree.sh -i usd/iesUp.usda -f 99:147 -s 8000
./genembree.sh -i usd/iesDown.usda -f 99:147 -s 8000
./luxtest_python.sh ./make_iesUp_iesDown_mp4.py -r embree