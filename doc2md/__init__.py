"""doc2md — convert documents to Markdown. CLI core, optional tkinter GUI.

Supports: PDF, DOC, DOCX, PPTX, XLSX, XLS, HTML, CSV, JSON, XML, TXT,
          images, email, EPUB, ZIP
"""

from doc2md.convert import convert_one

__version__ = "2.1.0"

__all__ = ["convert_one", "__version__"]
