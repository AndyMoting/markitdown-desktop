"""InkDrop 2.0 — Desktop shell for the web app."""
import threading
import uvicorn
import webview

from inkdrop.app import create_app


def start_server():
    uvicorn.run(create_app(), host="127.0.0.1", port=8000, log_level="warning")


if __name__ == "__main__":
    # Start FastAPI in background thread
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    # Create desktop window
    webview.create_window(
        "InkDrop · 喂给 AI 的文档预处理器",
        "http://127.0.0.1:8000",
        width=1100,
        height=750,
        min_size=(900, 600),
    )
    webview.start()
