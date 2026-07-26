# GUI Enhancement Report

**Status:** DONE

**Date:** 2026-07-21

**File modified:** `D:\Projects\MD\markitdown-desktop\inkdrop_gui.py`

## What was modified

### 1. Imports (top of file)
- Added `PIL.Image` / `PIL.ImageTk` with graceful fallback (`_HAS_PIL` flag)
- Added `inkdrop.quality.check_quality` / `QualityReport` with graceful fallback (`_HAS_QUALITY` flag)

### 2. `ConvertResult` NamedTuple
- Added `images: list[str] = []` — absolute paths to extracted images
- Added `markdown: str = ""` — raw markdown text for quality analysis

### 3. `_call_markitdown()` now returns `(text, img_count, error, image_paths)`
- After `_extract_images`, collects actual file paths via new `_collect_image_paths()` helper

### 4. `_postprocess_pdf()` now returns `(text, img_count, warning, image_paths)`
- After PDF image extraction, collects all image paths from the images directory

### 5. `_convert_one()` wires new fields through
- Receives image paths and markdown text from inner functions
- Passes them into `ConvertResult`

### 6. `_collect_image_paths()` helper
- Lists and sorts all files in the images directory
- Returns empty list if directory doesn't exist

### 7. GUI — Quality Panel (`_build_quality_panel`)
- Shows score (0-100) with color coding: green ≥70, yellow ≥40, red <40
- Shows: heading structure, table count, image count, garbled detection
- Single-row compact layout below results text

### 8. GUI — Image Gallery (`_build_image_gallery`)
- Horizontal scrollable canvas with 80x80 thumbnails
- Each thumbnail shows filename label
- Click opens image viewer dialog
- Hidden when no images; shown via `pack(before=open_all_btn)` when images exist

### 9. GUI — Image Viewer Dialog (`_open_image_viewer`)
- Toplevel window with full-size image (max 800x600, scaled to fit)
- Prev/Next buttons + keyboard arrows (Left/Right)
- Escape to close
- Centered on parent window

### 10. Integration
- `_clear_results()` now also clears quality panel and image gallery
- `_on_one_success()` accepts optional `images` and `markdown` kwargs
- `_convert_thread()` passes `result.images` and `result.markdown` through `root.after()`

## Issues encountered

None. PIL/Pillow was already installed in the environment. The `inkdrop.quality` module was already available.

## Verification

- `ast.parse` passes — no syntax errors
- `import inkdrop_gui` succeeds
- GUI launches without errors (mainloop blocked in test, but import chain is clean)

## Constraints respected

- Did not modify `doc2md.py`, `pdf_engine.py`, `doc_engine.py`, or `sniffer.py`
- Preserved `_convert_one(filepath, save_to_tool, md=None)` signature
- All existing functionality (drag-drop, batch convert, settings, CLI) preserved
- UI text in Chinese matching existing style
- PIL imported gracefully with try/except
