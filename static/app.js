const GMAPS_EMBED_API_KEY = window.GMAPS_EMBED_API_KEY;
const imageForm = document.querySelector("#image-form");
const videoForm = document.querySelector("#video-form");
const agentForm = document.querySelector("#agent-form");
const mergeForm = document.querySelector("#merge-form");
const imageResult = document.querySelector("#image-result");
const videoResult = document.querySelector("#video-result");
const agentLog = document.querySelector("#agent-log");
const agentFinal = document.querySelector("#agent-final");
const agentPreview = document.querySelector("#agent-preview");
const mergeResult = document.querySelector("#merge-result");
const mergeVideo = document.querySelector("#merge-video");
const adBadge = document.querySelector("#ad-badge");
const adProgress = document.querySelector("#ad-progress");
let lastGmapsResult = null;
function setResult(target, payload) {
  if (!target) return;
  target.textContent = JSON.stringify(payload, null, 2);
}
async function postJson(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) {
    throw data;
  }
  return data;
}
async function streamAgent(prompt) {
  if (agentLog)
    agentLog.innerHTML = "";
  if (agentFinal)
    agentFinal.textContent = "";
  if (agentPreview)
    agentPreview.innerHTML = "";
  lastGmapsResult = null;
  const response = await fetch("/api/agent", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt })
  });
  if (!response.body) {
    throw new Error("No response body for stream");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done)
      break;
    buffer += decoder.decode(value, { stream: true });
    let index = buffer.indexOf("\n\n");
    while (index !== -1) {
      const raw = buffer.slice(0, index).trim();
      buffer = buffer.slice(index + 2);
      if (raw.startsWith("data:")) {
        const jsonText = raw.replace(/^data:\s*/, "");
        const payload = JSON.parse(jsonText);
        renderAgentEvent(payload);
      }
      index = buffer.indexOf("\n\n");
    }
  }
}
function renderAgentEvent(payload) {
  storeGmapsResult(payload);
  const previewTargets = collectPreviewTargets(payload);
  if (previewTargets.length && agentPreview) {
    previewTargets.forEach((target) => {
      const node = renderPreview(target);
      if (node)
        agentPreview.appendChild(node);
    });
  }
  const type = String(payload.type || "");
  if (type === "final") {
    setResult(agentFinal, payload);
    if (lastGmapsResult && agentPreview) {
      const groundingNode = renderGmapsGrounding(lastGmapsResult);
      if (groundingNode)
        agentPreview.appendChild(groundingNode);
    }
    return;
  }
  const line = document.createElement("div");
  line.className = "log-item";
  line.textContent = JSON.stringify(payload, null, 2);
  agentLog === null || agentLog === void 0 ? void 0 : agentLog.appendChild(line);
}
function collectPreviewTargets(payload) {
  const targets = [];
  const seen = /* @__PURE__ */ new Set();
  const walk = (value, depth) => {
    if (depth > 4)
      return;
    if (typeof value === "string") {
      const maybe = value.trim();
      if (!maybe || seen.has(maybe))
        return;
      seen.add(maybe);
      addTargetFromValue(targets, maybe, "value");
      return;
    }
    if (Array.isArray(value)) {
      value.forEach((item) => walk(item, depth + 1));
      return;
    }
    if (value && typeof value === "object") {
      Object.values(value).forEach((item) => walk(item, depth + 1));
    }
  };
  walk(payload, 0);
  const text = collectText(payload);
  if (text) {
    extractPathsFromText(text).forEach((path) => {
      if (!seen.has(path)) {
        seen.add(path);
        addTargetFromValue(targets, path, "text");
      }
    });
  }
  return targets;
}
function renderGmapsGrounding(output) {
  const card = document.createElement("div");
  card.className = "grounding-card";
  const header = document.createElement("div");
  header.className = "grounding-header";
  const title = document.createElement("h3");
  title.className = "grounding-title";
  const badge = document.createElement("span");
  badge.className = "grounding-badge";
  badge.textContent = "GMAPS";
  header.appendChild(title);
  header.appendChild(badge);
  card.appendChild(header);
  if (output.status !== "success") {
    title.textContent = "Location lookup failed";
    const error = document.createElement("div");
    error.className = "grounding-error";
    error.textContent = String(output.error || "Unknown error");
    card.appendChild(error);
    return card;
  }
  const summary = output.summary || {};
  const details = output.details || {};
  const name = String(summary.name || details.name || "Location");
  title.textContent = name;
  const grid = document.createElement("dl");
  grid.className = "grounding-grid";
  addGroundingRow(grid, "Address", summary.formatted_address || details.formatted_address);
  addGroundingRow(
    grid,
    "Coordinates",
    formatLatLng(summary.location || getNested(details, ["geometry", "location"]))
  );
  addGroundingRow(grid, "Place ID", summary.place_id);
  addGroundingRow(grid, "Types", formatArray(summary.types || details.types));
  addGroundingRow(
    grid,
    "Rating",
    formatRating(summary.rating || details.rating, summary.user_ratings_total || details.user_ratings_total)
  );
  addGroundingRow(grid, "Business", details.business_status);
  addGroundingRow(grid, "Website", details.website);
  const mapLink = formatMapLink(summary.place_id);
  if (mapLink) {
    addGroundingRow(grid, "Maps", mapLink);
  }
  card.appendChild(grid);
  const mapFrame = renderGroundingMap(
    summary.place_id,
    summary.location || getNested(details, ["geometry", "location"])
  );
  if (mapFrame) {
    card.appendChild(mapFrame);
  }
  const weekdayText = getNested(details, ["opening_hours", "weekday_text"]);
  if (Array.isArray(weekdayText) && weekdayText.length) {
    const hours = document.createElement("div");
    hours.className = "grounding-hours";
    const label = document.createElement("div");
    label.className = "grounding-label";
    label.textContent = "Hours";
    const list = document.createElement("ul");
    weekdayText.forEach((line2) => {
      const item = document.createElement("li");
      item.textContent = String(line2);
      list.appendChild(item);
    });
    hours.appendChild(label);
    hours.appendChild(list);
    card.appendChild(hours);
  }
  return card;
}
function addGroundingRow(grid, label, value) {
  if (value === null || value === void 0 || value === "")
    return;
  const dt = document.createElement("dt");
  dt.textContent = label;
  const dd = document.createElement("dd");
  dd.textContent = String(value);
  grid.appendChild(dt);
  grid.appendChild(dd);
}
function formatLatLng(value) {
  if (!value || typeof value !== "object")
    return null;
  const rec = value;
  if (typeof rec.lat === "number" && typeof rec.lng === "number") {
    return `${rec.lat.toFixed(6)}, ${rec.lng.toFixed(6)}`;
  }
  return null;
}
function formatArray(value) {
  if (Array.isArray(value) && value.length) {
    return value.map((item) => String(item)).join(", ");
  }
  return null;
}
function formatRating(rating, total) {
  if (rating === null || rating === void 0)
    return null;
  if (typeof total === "number") {
    return `${rating} (${total} reviews)`;
  }
  return String(rating);
}
function formatMapLink(placeId) {
  if (!placeId)
    return null;
  return `https://www.google.com/maps/place/?q=place_id:${encodeURIComponent(
    String(placeId)
  )}`;
}
function renderGroundingMap(placeId, location) {
  if (!GMAPS_EMBED_API_KEY)
    return null;
  const src = buildEmbedUrl(placeId, location);
  if (!src)
    return null;
  const wrapper = document.createElement("div");
  wrapper.className = "grounding-map";
  const iframe = document.createElement("iframe");
  iframe.src = src;
  iframe.loading = "lazy";
  iframe.referrerPolicy = "no-referrer-when-downgrade";
  iframe.allowFullscreen = true;
  iframe.title = "Location map";
  wrapper.appendChild(iframe);
  return wrapper;
}
function buildEmbedUrl(placeId, location) {
  const key = encodeURIComponent(String(GMAPS_EMBED_API_KEY || ""));
  if (placeId) {
    return `https://www.google.com/maps/embed/v1/place?key=${key}&q=place_id:${encodeURIComponent(
      String(placeId)
    )}`;
  }
  const coords = formatLatLng(location);
  if (coords) {
    return `https://www.google.com/maps/embed/v1/view?key=${key}&center=${encodeURIComponent(
      coords
    )}&zoom=16`;
  }
  return null;
}
function getNested(value, path) {
  let current = value;
  for (const key of path) {
    if (!current || typeof current !== "object")
      return void 0;
    current = current[key];
  }
  return current;
}
function storeGmapsResult(payload) {
  if (payload.type === "tool_result" && payload.tool === "tool_gmaps_grounding") {
    const output = payload.output;
    if (output)
      lastGmapsResult = output;
    return;
  }
  if (payload.type === "final") {
    const result = payload.result;
    const response = (result == null ? void 0 : result.function_response) || null;
    if ((response == null ? void 0 : response.name) === "tool_gmaps_grounding") {
      const output = response.response;
      if (output)
        lastGmapsResult = output;
    }
  }
}
function collectText(payload) {
  const parts = [];
  const walk = (value, depth) => {
    if (depth > 4)
      return;
    if (typeof value === "string") {
      if (value.length < 5e3)
        parts.push(value);
      return;
    }
    if (Array.isArray(value)) {
      value.forEach((item) => walk(item, depth + 1));
      return;
    }
    if (value && typeof value === "object") {
      Object.values(value).forEach((item) => walk(item, depth + 1));
    }
  };
  walk(payload, 0);
  return parts.join(" ");
}
function extractPathsFromText(text) {
  const matches = text.match(/[\\w./-]+\\.(?:png|jpg|jpeg|webp|mp4|wav|mp3|aac)/gi);
  return matches ? Array.from(new Set(matches)) : [];
}
function addTargetFromValue(targets, value, hint) {
  if (typeof value !== "string" || !value)
    return;
  const url = value.startsWith("http") ? value : fileToUrl(value);
  const lower = value.toLowerCase();
  if (hint === "video_url" || lower.endsWith(".mp4")) {
    targets.push({ kind: "video", url });
    return;
  }
  if (lower.endsWith(".wav") || lower.endsWith(".mp3") || lower.endsWith(".aac")) {
    targets.push({ kind: "audio", url });
    return;
  }
  if (lower.endsWith(".png") || lower.endsWith(".jpg") || lower.endsWith(".jpeg") || lower.endsWith(".webp")) {
    targets.push({ kind: "image", url });
  }
}
function fileToUrl(path) {
  return `/files?path=${encodeURIComponent(path)}`;
}
function renderPreview(target) {
  if (target.kind === "image") {
    const img = document.createElement("img");
    img.src = target.url;
    img.alt = "Generated image";
    return img;
  }
  if (target.kind === "video") {
    const video = document.createElement("video");
    video.src = target.url;
    video.controls = true;
    return video;
  }
  if (target.kind === "audio") {
    const audio = document.createElement("audio");
    audio.src = target.url;
    audio.controls = true;
    return audio;
  }
  return null;
}
imageForm === null || imageForm === void 0 ? void 0 : imageForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(imageForm);
  const payload = Object.fromEntries(formData.entries());
  try {
    const data = await postJson("/api/generate-image", payload);
    setResult(imageResult, data);
  } catch (err) {
    setResult(imageResult, { status: "error", error: err });
  }
});
videoForm === null || videoForm === void 0 ? void 0 : videoForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(videoForm);
  const payload = Object.fromEntries(formData.entries());
  if (payload.duration_seconds) {
    payload.duration_seconds = Number(payload.duration_seconds);
  }
  if (payload.timeout) {
    payload.timeout = Number(payload.timeout);
  }
  try {
    const data = await postJson("/api/generate-video", payload);
    setResult(videoResult, data);
  } catch (err) {
    setResult(videoResult, { status: "error", error: err });
  }
});
agentForm === null || agentForm === void 0 ? void 0 : agentForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(agentForm);
  const prompt = String(formData.get("prompt") || "").trim();
  if (!prompt) {
    setResult(agentFinal, { status: "error", error: "Prompt is required" });
    return;
  }
  try {
    await streamAgent(prompt);
  } catch (err) {
    setResult(agentFinal, { status: "error", error: err });
  }
});
mergeForm === null || mergeForm === void 0 ? void 0 : mergeForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!mergeForm)
    return;
  const formData = new FormData(mergeForm);
  setResult(mergeResult, { status: "loading" });
  try {
    const response = await fetch("/api/merge-videos", {
      method: "POST",
      body: formData
    });
    const data = await response.json();
    if (!response.ok) {
      throw data;
    }
    setResult(mergeResult, data);
    if (mergeVideo && data.path) {
      mergeVideo.src = `/files?path=${encodeURIComponent(data.path)}`;
      mergeVideo.load();
      wireAdIndicator(mergeVideo, data.ad_start, data.ad_end);
      updateAdTimeline(data.ad_start, data.ad_end, mergeVideo);
    }
  } catch (err) {
    setResult(mergeResult, { status: "error", error: err });
  }
});
function wireAdIndicator(video, start, end) {
  const update = () => {
    const current = video.currentTime;
    if (adBadge) {
      adBadge.classList.toggle("active", current >= start && current <= end);
    }
  };
  video.addEventListener("timeupdate", update);
  video.addEventListener("seeked", update);
}
function updateAdTimeline(start, end, video) {
  const apply = () => {
    if (!adProgress)
      return;
    const duration = video.duration || 1;
    const left = Math.max(0, start / duration) * 100;
    const width = Math.max(0, (end - start) / duration) * 100;
    adProgress.style.left = `${left}%`;
    adProgress.style.width = `${width}%`;
  };
  if (video.readyState >= 1) {
    apply();
  } else {
    video.addEventListener("loadedmetadata", apply, { once: true });
  }
}
