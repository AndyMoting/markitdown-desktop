# Task 3 Report: Quality check module

## Status: DONE

## What I did

1. Created `tests/test_quality.py` with 7 test cases per the brief
2. Ran tests — confirmed `ModuleNotFoundError` (TDD red phase)
3. Created `inkdrop/quality.py` with:
   - `QualityReport` dataclass (score, heading_structure_ok, table_count, image_count, garbled_detected)
   - `check_quality(markdown: str) -> QualityReport` function
   - Pure functions, no I/O, no external deps beyond `re` and `dataclasses`
4. Ran tests — all 7 passed
5. Committed

## Test results

```
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-8.3.3, pluggy-1.6.0
collected 7 items

tests/test_quality.py::test_check_quality_returns_report PASSED          [ 14%]
tests/test_quality.py::test_quality_good_structure PASSED                [ 28%]
tests/test_quality.py::test_quality_broken_heading_hierarchy PASSED      [ 42%]
tests/test_quality.py::test_quality_detects_tables PASSED                [ 57%]
tests/test_quality.py::test_quality_detects_garbled PASSED               [ 71%]
tests/test_quality.py::test_quality_empty PASSED                         [ 85%]
tests/test_quality.py::test_quality_images PASSED                        [100%]

============================== 7 passed in 0.03s =============================
```

## Issues

None.
