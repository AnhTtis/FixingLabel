from pathlib import Path
import json

BASE_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BASE_DIR.parent
DATA_DIR = BASE_DIR / ".data"
DOCUMENTS_DIR = DATA_DIR / "documents"
SHARED_DIR = REPO_DIR / "shared" / "annotation-schema"
LOCAL_SCHEMA_DIR = REPO_DIR / "annotation-schema"
LABELS_PATH = SHARED_DIR / "labels.json"
SNAPSHOTS_DIR = REPO_DIR / "snapshots"


def resolve_labels_path(preferred: str | Path | None = None) -> Path:
    candidates: list[Path] = []
    if preferred:
        candidates.append(Path(preferred).expanduser())
    candidates.extend([
        LABELS_PATH,
        LOCAL_SCHEMA_DIR / "labels.json",
    ])

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]



def load_label_config(path: str | Path | None = None) -> dict:
    labels_path = resolve_labels_path(path)
    with labels_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)
