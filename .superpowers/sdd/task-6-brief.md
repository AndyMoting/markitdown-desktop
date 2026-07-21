# Task 6: Application entry point + smoke test

**Files to create:**
- `D:\Projects\MD\markitdown-desktop\run.py`
- `D:\Projects\MD\markitdown-desktop\inkdrop\__main__.py`

## Step 1: Create entry point scripts

Create `run.py` (project root):
```python
#!/usr/bin/env python3
"""Launch InkDrop web app."""
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "inkdrop.app:create_app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        factory=True,
    )
```

Create `inkdrop/__main__.py`:
```python
"""Run with `python -m inkdrop`."""
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "inkdrop.app:create_app",
        host="127.0.0.1",
        port=8000,
        factory=True,
    )
```

## Step 2: Verify app starts

Run: `D:\Projects\.venv\Scripts\python.exe -c "from inkdrop.app import create_app; app = create_app(); print('OK')"`
Expected: `OK`

## Step 3: Commit

```powershell
git add -A
git commit -m "feat: add launcher entry point"
```

## Global Constraints
- Do NOT modify existing files
