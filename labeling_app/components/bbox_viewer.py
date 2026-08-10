from __future__ import annotations

from typing import Any

import streamlit as st

HTML = """
<div class="bbox-viewer"></div>
"""

CSS = """
:host {
  display: block;
}

.bbox-viewer {
  width: 100%;
}

.viewer-shell {
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
}

.viewer-stage {
  position: relative;
  width: 100%;
  overflow: hidden;
  border: 1px solid var(--st-border-color, #d6ddf0);
  border-radius: 1rem;
  background: var(--st-secondary-background-color, #eef3ff);
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.08);
}

.viewer-image {
  display: block;
  width: 100%;
  height: auto;
  user-select: none;
  -webkit-user-drag: none;
}

.viewer-overlay {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}

.viewer-hint {
  font-size: 0.92rem;
  color: var(--st-text-color, #172033);
  opacity: 0.8;
}

.bbox-rect {
  fill-opacity: 0.12;
  stroke-width: 2;
  transition: fill-opacity 0.12s ease, stroke-width 0.12s ease;
}

.bbox-rect:hover {
  fill-opacity: 0.2;
}

.bbox-rect.selected {
  fill-opacity: 0.24;
  stroke-width: 3;
}

.bbox-handle {
  fill: #ffffff;
  stroke-width: 2;
  cursor: pointer;
}

.bbox-draft {
  fill: rgba(65, 89, 227, 0.15);
  stroke: var(--st-primary-color, #4159e3);
  stroke-width: 2;
  stroke-dasharray: 8 6;
}
"""

JS = """
const SVG_NS = 'http://www.w3.org/2000/svg';
const MIN_BOX_SIZE = 4;

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function normalizeBox(box) {
  const [x0, y0, x1, y1] = box;
  return [
    Math.min(x0, x1),
    Math.min(y0, y1),
    Math.max(x0, x1),
    Math.max(y0, y1),
  ];
}

function boxesAreDifferent(a, b) {
  if (!Array.isArray(a) || !Array.isArray(b) || a.length !== 4 || b.length !== 4) {
    return true;
  }
  return a.some((value, index) => Math.abs(value - b[index]) > 0.5);
}

function toPagePoint(event, svg, width, height) {
  const rect = svg.getBoundingClientRect();
  const x = ((event.clientX - rect.left) / rect.width) * width;
  const y = ((event.clientY - rect.top) / rect.height) * height;
  return {
    x: clamp(x, 0, width),
    y: clamp(y, 0, height),
  };
}

function makeSvgNode(name, attrs = {}) {
  const node = document.createElementNS(SVG_NS, name);
  Object.entries(attrs).forEach(([key, value]) => {
    if (value !== undefined && value !== null) {
      node.setAttribute(key, String(value));
    }
  });
  return node;
}

function applyBoxToRect(rect, box) {
  const [x0, y0, x1, y1] = box;
  rect.setAttribute('x', String(x0));
  rect.setAttribute('y', String(y0));
  rect.setAttribute('width', String(Math.max(0, x1 - x0)));
  rect.setAttribute('height', String(Math.max(0, y1 - y0)));
}

function getHandlePositions(box) {
  const [x0, y0, x1, y1] = box;
  return {
    nw: [x0, y0],
    ne: [x1, y0],
    sw: [x0, y1],
    se: [x1, y1],
  };
}

function updateHandles(handles, box) {
  const positions = getHandlePositions(box);
  Object.entries(handles).forEach(([key, node]) => {
    const [x, y] = positions[key];
    node.setAttribute('cx', String(x));
    node.setAttribute('cy', String(y));
  });
}

function createRectElement(box, color, selected, clickable, setTriggerValue) {
  const rect = makeSvgNode('rect', {
    rx: 4,
    ry: 4,
  });
  applyBoxToRect(rect, box.bbox);

  rect.classList.add('bbox-rect');
  if (selected) {
    rect.classList.add('selected');
  }

  rect.style.fill = color;
  rect.style.stroke = color;
  rect.style.cursor = clickable ? 'pointer' : 'default';
  rect.style.pointerEvents = clickable ? 'auto' : 'none';

  const title = makeSvgNode('title');
  title.textContent = `${box.label}${box.text ? ' — ' + box.text : ''}`;
  rect.appendChild(title);

  if (clickable) {
    rect.addEventListener('click', (event) => {
      event.stopPropagation();
      setTriggerValue('selected', box.id);
    });
  }

  return rect;
}

function createHandle(name, x, y, color) {
  const cursors = {
    nw: 'nwse-resize',
    se: 'nwse-resize',
    ne: 'nesw-resize',
    sw: 'nesw-resize',
  };

  const handle = makeSvgNode('circle', {
    cx: x,
    cy: y,
    r: 6,
  });
  handle.classList.add('bbox-handle');
  handle.style.stroke = color;
  handle.style.cursor = cursors[name] || 'pointer';
  return handle;
}

function buildMoveBox(startBox, dx, dy, pageWidth, pageHeight) {
  const width = startBox[2] - startBox[0];
  const height = startBox[3] - startBox[1];
  const left = clamp(startBox[0] + dx, 0, pageWidth - width);
  const top = clamp(startBox[1] + dy, 0, pageHeight - height);
  return [left, top, left + width, top + height];
}

function buildResizeBox(startBox, handle, point, pageWidth, pageHeight) {
  let [x0, y0, x1, y1] = startBox;

  if (handle.includes('w')) {
    x0 = clamp(point.x, 0, x1 - MIN_BOX_SIZE);
  }
  if (handle.includes('e')) {
    x1 = clamp(point.x, x0 + MIN_BOX_SIZE, pageWidth);
  }
  if (handle.includes('n')) {
    y0 = clamp(point.y, 0, y1 - MIN_BOX_SIZE);
  }
  if (handle.includes('s')) {
    y1 = clamp(point.y, y0 + MIN_BOX_SIZE, pageHeight);
  }

  return normalizeBox([x0, y0, x1, y1]);
}

export default function(component) {
  const { data, parentElement, setTriggerValue } = component;
  const root = parentElement.querySelector('.bbox-viewer');
  if (!root) {
    return;
  }

  if (!root.__mounted) {
    root.innerHTML = `
      <div class="viewer-shell">
        <div class="viewer-stage">
          <img class="viewer-image" alt="PDF page preview" draggable="false" />
          <svg class="viewer-overlay" preserveAspectRatio="xMidYMid meet"></svg>
        </div>
        <div class="viewer-hint"></div>
      </div>
    `;
    root.__mounted = true;
  }

  const image = root.querySelector('.viewer-image');
  const svg = root.querySelector('.viewer-overlay');
  const hint = root.querySelector('.viewer-hint');
  const pageWidth = Number(data?.pageWidth || 1);
  const pageHeight = Number(data?.pageHeight || 1);
  const mode = data?.mode || 'edit';
  const boxes = Array.isArray(data?.boxes) ? data.boxes : [];
  const selectedId = data?.selectedId || null;
  const pendingBox = Array.isArray(data?.pendingBox) ? data.pendingBox : null;
  const colors = data?.colors || {};

  image.src = data?.imageSrc || '';
  svg.setAttribute('viewBox', `0 0 ${pageWidth} ${pageHeight}`);
  svg.innerHTML = '';

  const resetWindowHandlers = () => {
    if (root.__moveHandler) {
      window.removeEventListener('pointermove', root.__moveHandler);
      root.__moveHandler = null;
    }
    if (root.__upHandler) {
      window.removeEventListener('pointerup', root.__upHandler);
      root.__upHandler = null;
    }
  };

  resetWindowHandlers();

  const background = makeSvgNode('rect', {
    x: 0,
    y: 0,
    width: pageWidth,
    height: pageHeight,
    fill: 'transparent',
  });
  svg.appendChild(background);

  let selectedRect = null;
  let selectedBox = null;

  boxes.forEach((box) => {
    const color = colors[box.label] || 'var(--st-primary-color, #4159e3)';
    const isSelected = box.id === selectedId;
    const rect = createRectElement(box, color, isSelected, true, setTriggerValue);
    if (isSelected) {
      selectedRect = rect;
      selectedBox = box;
    }
    svg.appendChild(rect);
  });

  if (pendingBox && pendingBox.length === 4) {
    const draftRect = makeSvgNode('rect', {
      rx: 4,
      ry: 4,
    });
    draftRect.classList.add('bbox-draft');
    applyBoxToRect(draftRect, normalizeBox(pendingBox));
    draftRect.style.pointerEvents = 'none';
    svg.appendChild(draftRect);
  }

  if (mode === 'edit') {
    hint.textContent = 'Click để chọn bbox. Kéo khung để di chuyển hoặc kéo các nút tròn ở góc để resize trực tiếp.';
    background.style.cursor = 'default';
    background.addEventListener('click', () => {
      setTriggerValue('selected', '__clear__');
    });

    if (selectedBox && selectedRect) {
      const selectedColor = colors[selectedBox.label] || 'var(--st-primary-color, #4159e3)';
      const handleNodes = {};
      const handlePositions = getHandlePositions(selectedBox.bbox);

      Object.entries(handlePositions).forEach(([name, [x, y]]) => {
        const handle = createHandle(name, x, y, selectedColor);
        handleNodes[name] = handle;
        svg.appendChild(handle);
      });

      const startInteraction = (kind, handleName = null) => (event) => {
        event.stopPropagation();
        event.preventDefault();

        const startPoint = toPagePoint(event, svg, pageWidth, pageHeight);
        const startBox = [...selectedBox.bbox];
        let previewBox = [...selectedBox.bbox];

        const handleMove = (moveEvent) => {
          const point = toPagePoint(moveEvent, svg, pageWidth, pageHeight);
          if (kind === 'move') {
            previewBox = buildMoveBox(
              startBox,
              point.x - startPoint.x,
              point.y - startPoint.y,
              pageWidth,
              pageHeight,
            );
          } else {
            previewBox = buildResizeBox(startBox, handleName, point, pageWidth, pageHeight);
          }

          applyBoxToRect(selectedRect, previewBox);
          updateHandles(handleNodes, previewBox);
        };

        const handleUp = () => {
          resetWindowHandlers();
          if (boxesAreDifferent(startBox, previewBox)) {
            setTriggerValue('bbox_changed', {
              id: selectedBox.id,
              bbox: previewBox,
            });
          }
        };

        root.__moveHandler = handleMove;
        root.__upHandler = handleUp;
        window.addEventListener('pointermove', handleMove);
        window.addEventListener('pointerup', handleUp, { once: true });
      };

      selectedRect.style.cursor = 'move';
      selectedRect.addEventListener('pointerdown', startInteraction('move'));
      Object.entries(handleNodes).forEach(([name, handle]) => {
        handle.addEventListener('pointerdown', startInteraction('resize', name));
      });
    }
  } else {
    hint.textContent = 'Kéo chuột trên trang để tạo bbox mới. Sau đó điền label và thông tin chi tiết ở panel bên phải.';
    background.style.cursor = 'crosshair';
    background.addEventListener('pointerdown', (event) => {
      const start = toPagePoint(event, svg, pageWidth, pageHeight);
      const draftRect = makeSvgNode('rect', {
        x: start.x,
        y: start.y,
        width: 0,
        height: 0,
        rx: 4,
        ry: 4,
      });
      draftRect.classList.add('bbox-draft');
      draftRect.style.pointerEvents = 'none';
      svg.appendChild(draftRect);

      const handleMove = (moveEvent) => {
        const point = toPagePoint(moveEvent, svg, pageWidth, pageHeight);
        const previewBox = normalizeBox([start.x, start.y, point.x, point.y]);
        applyBoxToRect(draftRect, previewBox);
      };

      const handleUp = (upEvent) => {
        const point = toPagePoint(upEvent, svg, pageWidth, pageHeight);
        const previewBox = normalizeBox([start.x, start.y, point.x, point.y]);
        resetWindowHandlers();
        draftRect.remove();

        if (previewBox[2] - previewBox[0] >= 3 && previewBox[3] - previewBox[1] >= 3) {
          setTriggerValue('draft_bbox', {
            bbox: previewBox,
          });
        }
      };

      root.__moveHandler = handleMove;
      root.__upHandler = handleUp;
      window.addEventListener('pointermove', handleMove);
      window.addEventListener('pointerup', handleUp, { once: true });
    });
  }

  return () => {
    resetWindowHandlers();
  };
}
"""

_VIEWER_COMPONENT = st.components.v2.component(
    "pdf_bbox_viewer",
    html=HTML,
    css=CSS,
    js=JS,
)



def bbox_viewer(
    *,
    image_src: str,
    page_width: float,
    page_height: float,
    boxes: list[dict[str, Any]],
    mode: str,
    selected_id: str | None,
    colors: dict[str, str],
    pending_box: list[float] | None,
    key: str,
) -> dict[str, Any]:
    result = _VIEWER_COMPONENT(
        key=key,
        data={
            "imageSrc": image_src,
            "pageWidth": page_width,
            "pageHeight": page_height,
            "boxes": boxes,
            "mode": mode,
            "selectedId": selected_id,
            "colors": colors,
            "pendingBox": pending_box,
        },
        on_selected_change=lambda: None,
        on_draft_bbox_change=lambda: None,
        on_bbox_changed_change=lambda: None,
        width="stretch",
        height="content",
    )

    return {
        "selected": getattr(result, "selected", None),
        "draft_bbox": getattr(result, "draft_bbox", None),
        "bbox_changed": getattr(result, "bbox_changed", None),
    }
