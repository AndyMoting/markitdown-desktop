# Task 6 Report: Application entry point + smoke test

## Status: ✅ Complete

## Files created
- `run.py` — launcher with reload for development
- `inkdrop/__main__.py` — enables `python -m inkdrop`

## Verification

```
D:\Projects\.venv\Scripts\python.exe -c "from inkdrop.app import create_app; app = create_app(); print('OK')"
→ OK
```

## Commit
- `a8f92b3` feat: add launcher entry point
