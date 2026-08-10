---
title: FixingLabel
sdk: streamlit
sdk_version: 1.60.0
python_version: "3.11"
app_file: streamlit_app.py
---

# FixingLabel

FixingLabel is a **Streamlit PDF annotation editor** for both local review workflows and web deployment.

## What it does

- upload a PDF and annotation JSON for web use, or open local files by path on desktop
- accept both the canonical JSON schema and looser legacy JSON layouts
- render each PDF page as an image-backed canvas
- drag, resize, and draw bounding boxes on the canvas
- edit a box label ID and precise numeric bbox values
- delete a selected box from the properties panel
- edit **label display names** without changing the canonical label IDs stored in annotations
- save annotation and label changes directly back to disk in local path mode
- keep edits in session state and let users download the current JSON files in web upload mode

## Core design

- canonical bbox coordinates stay in **PDF space**
- annotation elements keep stable `label` **IDs**
- label display names are editable UI metadata loaded from the configured labels JSON file
- the Streamlit app keeps one active document in session state and does not keep rendered page images in Python state
- canvas interactions use `streamlit-drawable-canvas` while backend services still own geometry conversion and patch application
- backend services under `backend/app/services/` remain the source of truth for normalization, rendering, coordinate transforms, and patch application

## Repository layout

```text
streamlit_app.py                 Streamlit editor entrypoint
requirements.txt                 Runtime dependencies for local use and Streamlit deployment
annotation-schema/               Annotation schema and default label definitions
backend/app/                     Reusable Python schemas and services
sample_data/                     Example annotation payload
```

## Install locally

```powershell
python -m venv backend/.venv
backend/.venv/Scripts/pip install -r requirements.txt
```

## Run locally

```powershell
backend/.venv/Scripts/streamlit run streamlit_app.py
```

## Main workflow

### Web / deployed mode

1. Start the Streamlit app.
2. Upload a PDF and annotation JSON in the sidebar.
3. Optionally upload a labels JSON file.
4. Pick a page.
5. Use **Select / resize** mode to drag or resize boxes on the canvas.
6. Use **Draw new boxes** mode to add boxes with the chosen default label.
7. Click **Apply canvas changes**.
8. Edit label display names if needed.
9. Download the current annotation JSON and labels JSON.

### Local desktop mode

1. Switch the sidebar input mode to **Local file paths**.
2. Enter the PDF path and annotation JSON path.
3. Optionally choose a labels JSON path, or keep the detected default.
4. Load the document.
5. Edit boxes from the canvas or properties panel.
6. Save changes; local path mode writes them back to disk immediately.

## Deploy to Hugging Face Spaces

This repo is set up for a **Streamlit Space**:

- `README.md` contains Streamlit Spaces front matter
- `requirements.txt` installs the runtime dependencies needed by the Streamlit app
- `streamlit_app.py` is the configured app entrypoint

Typical flow:

1. Create a new Hugging Face Space with the **Streamlit** SDK.
2. Push this repository to the Space.
3. Let Spaces install from `requirements.txt` and launch `streamlit_app.py`.

## Notes

- `sample_data/sample.annotations.json` is included as a valid example annotation file.
- If `shared/annotation-schema/labels.json` is absent, the app falls back to `annotation-schema/labels.json`.
- Canvas deletion is still explicit from the properties panel; missing boxes on the canvas are not auto-deleted when you apply changes.
- In web upload mode, edits live in Streamlit session state until the user downloads the JSON files.
- In local path mode, annotation and label edits are written back to disk immediately.
