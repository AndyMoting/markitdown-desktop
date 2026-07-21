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
