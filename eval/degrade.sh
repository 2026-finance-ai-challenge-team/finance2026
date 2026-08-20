#!/usr/bin/env bash
# 합성 PDF -> 스캔·기울어짐·저조도·흐림 이미지 + 1쪽만 스캔본인 혼합 PDF.
# 실제 변환은 degrade.py가 한다. pdftoppm·ImageMagick·qpdf를 따로 깔지 않기 위해서다.
set -euo pipefail
cd "$(dirname "$0")"
exec "${PYTHON:-python3}" degrade.py "$@"
