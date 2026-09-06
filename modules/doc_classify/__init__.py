"""문서 분류 모듈 (담당: 연우).

사용자가 올린 파일이 **무슨 문서인지** 결정해 다음 단계로 넘긴다.
다섯 상태 판정은 하지 않는다. 설계 근거는 `docs/DOC_CLASSIFY.md`.
"""

from .classify import classify_files, load_signatures, load_task
from .metadata import extract_file_metadata

__all__ = ["classify_files", "extract_file_metadata", "load_signatures", "load_task"]
