"""Run with `python -m inkdrop`."""
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "inkdrop.app:create_app",
        host="127.0.0.1",
        port=8000,
        factory=True,
    )
