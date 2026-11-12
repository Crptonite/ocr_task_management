/* Document scanner: phone/webcam capture -> crop -> rotate -> enhance -> JPEG File.
 *
 * Scanner.open() returns a Promise<File | null>. Call it straight from a click handler:
 * when the live camera is unavailable (no getUserMedia, or plain http on a phone over LAN)
 * it falls back to <input capture="environment">, which only opens inside a user gesture.
 */
(() => {
  const MAX_EDGE = 2200; // long edge of the uploaded scan, enough for OCR without huge files
  const JPEG_QUALITY = 0.88;
  const HANDLE = 22; // corner hit radius in CSS px

  const el = (tag, attrs = {}, html = "") => {
    const n = document.createElement(tag);
    Object.entries(attrs).forEach(([k, v]) => n.setAttribute(k, v));
    n.innerHTML = html;
    return n;
  };

  const root = el("div", { class: "modal-backdrop scanner", id: "scanner-modal", hidden: "", role: "dialog", "aria-modal": "true", "aria-labelledby": "scanner-title" }, `
    <div class="modal-box scanner-box">
      <p class="modal-eyebrow">Scan document</p>
      <h3 id="scanner-title">Point the camera at the page</h3>
      <div class="scanner-stage" data-stage="camera">
        <video playsinline muted autoplay></video>
        <div class="scanner-guide" aria-hidden="true"></div>
      </div>
      <div class="scanner-stage" data-stage="edit" hidden>
        <canvas></canvas>
      </div>
      <p class="muted scanner-hint" data-hint></p>
      <div class="modal-actions scanner-actions">
        <button type="button" class="btn btn-outline" data-act="cancel">Cancel</button>
        <span class="scanner-spacer"></span>
        <button type="button" class="btn btn-outline" data-act="pick" data-on="camera">Use photo</button>
        <button type="button" class="btn btn-solid" data-act="shoot" data-on="camera">Capture</button>
        <button type="button" class="btn btn-outline" data-act="retake" data-on="edit">Retake</button>
        <button type="button" class="btn btn-outline" data-act="rotate" data-on="edit" title="Rotate 90°">Rotate</button>
        <button type="button" class="btn btn-outline" data-act="enhance" data-on="edit" aria-pressed="true">Enhance: on</button>
        <button type="button" class="btn btn-solid" data-act="use" data-on="edit">Use scan</button>
      </div>
    </div>`);
  const picker = el("input", { type: "file", accept: "image/*", capture: "environment", hidden: "" });
  document.body.append(root, picker);

  const $ = (s) => root.querySelector(s);
  const video = $("video");
  const canvas = $("canvas");
  const ctx = canvas.getContext("2d");
  const hint = $("[data-hint]");

  let resolveFn = null;
  let stream = null;
  let source = null; // canvas holding the (rotated) full-resolution photo
  let crop = null; // {x, y, w, h} in source pixels
  let enhance = true;
  let drag = null;
  let view = { scale: 1 }; // display px per source px

  const canStream = () => !!(navigator.mediaDevices?.getUserMedia && window.isSecureContext);

  function setStage(name) {
    root.querySelectorAll("[data-stage]").forEach((s) => (s.hidden = s.dataset.stage !== name));
    root.querySelectorAll("[data-on]").forEach((b) => (b.hidden = b.dataset.on !== name));
    $("#scanner-title").textContent = name === "camera" ? "Point the camera at the page" : "Adjust the crop";
    hint.textContent =
      name === "camera"
        ? "Fill the frame with the invoice, keep it flat and well lit."
        : "Drag the corners or edges to trim the background.";
  }

  function stopCamera() {
    stream?.getTracks().forEach((t) => t.stop());
    stream = null;
    video.srcObject = null;
  }

  function finish(file) {
    drag = null;
    stopCamera();
    root.hidden = true;
    source = null;
    const r = resolveFn;
    resolveFn = null;
    r?.(file);
  }

  async function startCamera() {
    setStage("camera");
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" }, width: { ideal: 3840 }, height: { ideal: 2160 } },
        audio: false,
      });
      video.srcObject = stream;
    } catch (err) {
      hint.textContent = `Camera unavailable (${err.name || err.message}). Use "Use photo" to take or pick one instead.`;
    }
  }

  function open() {
    if (resolveFn) return Promise.resolve(null);
    const p = new Promise((r) => (resolveFn = r));
    root.hidden = false;
    if (canStream()) {
      startCamera();
    } else {
      // No live preview here (e.g. http on a phone): open the native camera directly.
      setStage("camera");
      $("[data-act=shoot]").hidden = true;
      hint.textContent = "Opening your camera… If nothing happens, tap \"Use photo\".";
      picker.click();
    }
    return p;
  }

  /* ---------- Capture ---------- */

  function shoot() {
    if (!video.videoWidth) return;
    const c = document.createElement("canvas");
    c.width = video.videoWidth;
    c.height = video.videoHeight;
    c.getContext("2d").drawImage(video, 0, 0);
    stopCamera();
    loadSource(c);
  }

  picker.addEventListener("change", async () => {
    const file = picker.files[0];
    picker.value = "";
    if (!file) return;
    try {
      const bmp = await createImageBitmap(file, { imageOrientation: "from-image" });
      const c = document.createElement("canvas");
      c.width = bmp.width;
      c.height = bmp.height;
      c.getContext("2d").drawImage(bmp, 0, 0);
      bmp.close?.();
      stopCamera();
      loadSource(c);
    } catch {
      hint.textContent = "That image could not be read. Try a JPG or PNG.";
    }
  });

  function loadSource(c) {
    source = c;
    crop = autoCrop(c);
    setStage("edit");
    requestAnimationFrame(draw);
  }

  /* ---------- Auto crop: bounding box of the bright paper area ---------- */

  function autoCrop(src) {
    const s = Math.min(1, 240 / Math.max(src.width, src.height));
    const w = Math.max(1, Math.round(src.width * s));
    const h = Math.max(1, Math.round(src.height * s));
    const t = document.createElement("canvas");
    t.width = w;
    t.height = h;
    const tc = t.getContext("2d", { willReadFrequently: true });
    tc.drawImage(src, 0, 0, w, h);
    const px = tc.getImageData(0, 0, w, h).data;
    const gray = new Uint8Array(w * h);
    const hist = new Array(256).fill(0);
    for (let i = 0; i < w * h; i++) {
      const g = (px[i * 4] * 299 + px[i * 4 + 1] * 587 + px[i * 4 + 2] * 114) / 1000;
      gray[i] = g;
      hist[g | 0]++;
    }
    const thr = otsu(hist, w * h);
    const rows = new Array(h).fill(0);
    const cols = new Array(w).fill(0);
    for (let y = 0; y < h; y++)
      for (let x = 0; x < w; x++)
        if (gray[y * w + x] > thr) {
          rows[y]++;
          cols[x]++;
        }
    const span = (arr, len) => {
      let a = 0;
      let b = arr.length - 1;
      while (a < b && arr[a] < len * 0.35) a++;
      while (b > a && arr[b] < len * 0.35) b--;
      return [a, b];
    };
    const [y0, y1] = span(rows, w);
    const [x0, x1] = span(cols, h);
    const box = { x: x0 / s, y: y0 / s, w: (x1 - x0 + 1) / s, h: (y1 - y0 + 1) / s };
    // Not confident (paper fills the frame, or nothing paper-like found): keep the whole photo.
    const area = (box.w * box.h) / (src.width * src.height);
    if (area < 0.15 || area > 0.97) return { x: 0, y: 0, w: src.width, h: src.height };
    const pad = 0.01 * Math.max(src.width, src.height);
    return clampCrop({ x: box.x - pad, y: box.y - pad, w: box.w + 2 * pad, h: box.h + 2 * pad });
  }

  function otsu(hist, total) {
    let sum = 0;
    for (let i = 0; i < 256; i++) sum += i * hist[i];
    let sumB = 0, wB = 0, best = 0, thr = 127;
    for (let i = 0; i < 256; i++) {
      wB += hist[i];
      if (!wB) continue;
      const wF = total - wB;
      if (!wF) break;
      sumB += i * hist[i];
      const mB = sumB / wB;
      const mF = (sum - sumB) / wF;
      const between = wB * wF * (mB - mF) ** 2;
      if (between > best) {
        best = between;
        thr = i;
      }
    }
    return thr;
  }

  function clampCrop(c) {
    const min = 40;
    const x = Math.max(0, Math.min(c.x, source.width - min));
    const y = Math.max(0, Math.min(c.y, source.height - min));
    const w = Math.max(min, Math.min(c.w + (c.x - x), source.width - x));
    const h = Math.max(min, Math.min(c.h + (c.y - y), source.height - y));
    return { x, y, w, h };
  }

  /* ---------- Editor ---------- */

  function draw() {
    if (!source) return;
    const stage = $("[data-stage=edit]");
    // Collapse the canvas first so the stage reports the space available, not the old canvas size.
    canvas.style.width = canvas.style.height = "0px";
    const maxW = stage.clientWidth || 600;
    const maxH = Math.min(window.innerHeight * 0.58, 640);
    view.scale = Math.min(maxW / source.width, maxH / source.height);
    const dpr = window.devicePixelRatio || 1;
    const cw = Math.round(source.width * view.scale);
    const ch = Math.round(source.height * view.scale);
    canvas.style.width = cw + "px";
    canvas.style.height = ch + "px";
    canvas.width = cw * dpr;
    canvas.height = ch * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.drawImage(source, 0, 0, cw, ch);

    const s = view.scale;
    const r = { x: crop.x * s, y: crop.y * s, w: crop.w * s, h: crop.h * s };
    ctx.fillStyle = "rgba(0,0,0,.55)";
    ctx.beginPath();
    ctx.rect(0, 0, cw, ch);
    ctx.rect(r.x, r.y, r.w, r.h);
    ctx.fill("evenodd");
    ctx.strokeStyle = "#c8a27a";
    ctx.lineWidth = 2;
    ctx.strokeRect(r.x, r.y, r.w, r.h);
    ctx.fillStyle = "#c8a27a";
    for (const [x, y] of corners(r)) {
      ctx.beginPath();
      ctx.arc(x, y, 7, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  const corners = (r) => [
    [r.x, r.y],
    [r.x + r.w, r.y],
    [r.x, r.y + r.h],
    [r.x + r.w, r.y + r.h],
  ];

  function hitTest(px, py) {
    const s = view.scale;
    const r = { x: crop.x * s, y: crop.y * s, w: crop.w * s, h: crop.h * s };
    const near = (a, b) => Math.abs(a - b) <= HANDLE;
    const inX = px > r.x - HANDLE && px < r.x + r.w + HANDLE;
    const inY = py > r.y - HANDLE && py < r.y + r.h + HANDLE;
    const edges = {
      l: near(px, r.x) && inY,
      r: near(px, r.x + r.w) && inY,
      t: near(py, r.y) && inX,
      b: near(py, r.y + r.h) && inX,
    };
    const mode = Object.keys(edges).filter((k) => edges[k]).join("");
    if (mode) return mode;
    if (px > r.x && px < r.x + r.w && py > r.y && py < r.y + r.h) return "move";
    return null;
  }

  const pointer = (e) => {
    const b = canvas.getBoundingClientRect();
    return [e.clientX - b.left, e.clientY - b.top];
  };

  canvas.addEventListener("pointerdown", (e) => {
    if (!source) return;
    const [px, py] = pointer(e);
    const mode = hitTest(px, py);
    if (!mode) return;
    canvas.setPointerCapture(e.pointerId);
    drag = { mode, px, py, start: { ...crop } };
    e.preventDefault();
  });

  canvas.addEventListener("pointermove", (e) => {
    if (!source) return;
    const [px, py] = pointer(e);
    if (!drag) {
      const m = hitTest(px, py);
      canvas.style.cursor = !m ? "default" : m === "move" ? "move" : /^(lt|tl|rb|br)$/.test(m) ? "nwse-resize" : /^(rt|tr|lb|bl)$/.test(m) ? "nesw-resize" : /[lr]/.test(m) ? "ew-resize" : "ns-resize";
      return;
    }
    const dx = (px - drag.px) / view.scale;
    const dy = (py - drag.py) / view.scale;
    const c = { ...drag.start };
    if (drag.mode === "move") {
      c.x = Math.max(0, Math.min(source.width - c.w, c.x + dx));
      c.y = Math.max(0, Math.min(source.height - c.h, c.y + dy));
    } else {
      const m = drag.mode;
      const min = 40;
      if (m.includes("l")) { const nx = Math.max(0, Math.min(c.x + c.w - min, c.x + dx)); c.w += c.x - nx; c.x = nx; }
      if (m.includes("t")) { const ny = Math.max(0, Math.min(c.y + c.h - min, c.y + dy)); c.h += c.y - ny; c.y = ny; }
      if (m.includes("r")) c.w = Math.max(min, Math.min(source.width - c.x, c.w + dx));
      if (m.includes("b")) c.h = Math.max(min, Math.min(source.height - c.y, c.h + dy));
    }
    crop = c;
    draw();
  });

  const endDrag = () => (drag = null);
  canvas.addEventListener("pointerup", endDrag);
  canvas.addEventListener("pointercancel", endDrag);
  addEventListener("resize", () => !root.hidden && source && draw());

  function rotate() {
    const c = document.createElement("canvas");
    c.width = source.height;
    c.height = source.width;
    const cc = c.getContext("2d");
    cc.translate(c.width, 0);
    cc.rotate(Math.PI / 2);
    cc.drawImage(source, 0, 0);
    // Keep the user's crop, rotated with the image.
    const { x, y, w, h } = crop;
    source = c;
    crop = clampCrop({ x: c.width - (y + h), y: x, w: h, h: w });
    draw();
  }

  /* ---------- Output ---------- */

  // Grayscale + contrast stretch (1st..99th percentile) + slight gamma: whiter paper, darker ink.
  function enhanceImage(c) {
    const cc = c.getContext("2d", { willReadFrequently: true });
    const img = cc.getImageData(0, 0, c.width, c.height);
    const d = img.data;
    const n = d.length / 4;
    const hist = new Uint32Array(256);
    for (let i = 0; i < d.length; i += 4) {
      const g = (d[i] * 299 + d[i + 1] * 587 + d[i + 2] * 114) / 1000;
      d[i] = g;
      hist[g | 0]++;
    }
    const pct = (p) => {
      let acc = 0;
      for (let i = 0; i < 256; i++) if ((acc += hist[i]) >= n * p) return i;
      return 255;
    };
    const lo = pct(0.01);
    const hi = Math.max(lo + 1, pct(0.99));
    const lut = new Uint8ClampedArray(256);
    for (let i = 0; i < 256; i++) lut[i] = 255 * Math.pow(Math.min(1, Math.max(0, (i - lo) / (hi - lo))), 1.15);
    for (let i = 0; i < d.length; i += 4) d[i] = d[i + 1] = d[i + 2] = lut[d[i] | 0];
    cc.putImageData(img, 0, 0);
  }

  function exportScan() {
    const s = Math.min(1, MAX_EDGE / Math.max(crop.w, crop.h));
    const out = document.createElement("canvas");
    out.width = Math.round(crop.w * s);
    out.height = Math.round(crop.h * s);
    const oc = out.getContext("2d");
    oc.imageSmoothingQuality = "high";
    oc.drawImage(source, crop.x, crop.y, crop.w, crop.h, 0, 0, out.width, out.height);
    if (enhance) enhanceImage(out);
    return new Promise((resolve) => out.toBlob(resolve, "image/jpeg", JPEG_QUALITY));
  }

  const stamp = () => new Date().toISOString().slice(0, 19).replace(/[-:]/g, "").replace("T", "-");

  /* ---------- Buttons ---------- */

  root.addEventListener("click", async (e) => {
    if (e.target === root) return finish(null);
    const act = e.target.closest("[data-act]")?.dataset.act;
    if (act === "cancel") finish(null);
    else if (act === "shoot") shoot();
    else if (act === "pick") picker.click();
    else if (act === "retake") {
      source = null;
      canStream() ? startCamera() : (setStage("camera"), ($("[data-act=shoot]").hidden = true), picker.click());
    } else if (act === "rotate") rotate();
    else if (act === "enhance") {
      enhance = !enhance;
      e.target.textContent = `Enhance: ${enhance ? "on" : "off"}`;
      e.target.setAttribute("aria-pressed", String(enhance));
    } else if (act === "use") {
      if (!source) return;
      e.target.disabled = true;
      const blob = await exportScan();
      e.target.disabled = false;
      finish(blob ? new File([blob], `scan-${stamp()}.jpg`, { type: "image/jpeg" }) : null);
    }
  });

  addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !root.hidden) finish(null);
  });

  window.Scanner = { open };
})();
