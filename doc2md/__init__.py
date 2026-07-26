"""doc2md — convert documents to Markdown via CLI. Zero GUI dependencies.

Supports: PDF, DOC, DOCX, PPTX, XLSX, XLS, HTML, CSV, JSON, XML, TXT,
          images, email, EPUB, ZIP
"""

from doc2md.convert import convert_one

__version__ = "2.0.0"

__all__ = ["convert_one", "__version__"]
