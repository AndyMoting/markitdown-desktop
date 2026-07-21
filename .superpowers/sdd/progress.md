# SDD Progress Ledger

## Plan: InkDrop 2.0
## Date: 2026-07-21

| Task | Status | Commits | Notes |
|------|--------|---------|-------|
| 1: Project structure + dependencies | complete | 2921507 | All deps installed, packages created |
| 2: Converter module | complete | (after 2921507) | Tests pass, wraps doc2md pipeline |
| 3: Quality check module | complete | (after T2) | 7/7 tests pass |
| 4: Job manager | complete | d18ef6c | 4/4 tests pass |
| 5: FastAPI app + routes | complete | 1eaa755 + c2b3088 | 4/4 tests pass, deprecation fix |
| 6: Entry point + smoke test | complete | a8f92b3 | App starts OK |
| 7: Allure reporting | complete | bff06b7 | 18/18 tests pass, smoke test caught download bug |
| 8: Temp file cleanup | complete | b62a3c8 + a4138fe | Cleanup scheduler + fixture fix |
