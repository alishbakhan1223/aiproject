import axios from "axios";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export const api = axios.create({ baseURL: API_BASE, timeout: 10000 });

// Attach the JWT (if we have one) to every outgoing request automatically
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("cctv_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// If a protected call comes back 401 (expired/invalid token), force re-login
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem("cctv_token");
      window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);

// --- Auth ---
export const login = (username, password) => {
  const form = new URLSearchParams();
  form.append("username", username);
  form.append("password", password);
  return api
    .post("/auth/login", form, {
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    })
    .then((r) => r.data);
};

// --- Read-only data ---
export const getEvents = (eventType) =>
  api.get("/events", { params: eventType ? { event_type: eventType } : {} }).then((r) => r.data);
export const getAlerts = () => api.get("/alerts").then((r) => r.data);
export const getStatistics = () => api.get("/statistics").then((r) => r.data);
export const getKnownFaces = () => api.get("/known-faces").then((r) => r.data);
export const getCameras = () => api.get("/camera/list").then((r) => r.data);
export const getHealth = () => api.get("/health").then((r) => r.data);
export const getZone = (cameraId) => api.get(`/zones/${cameraId}`).then((r) => r.data);

// --- Mutating (require login) ---
export const addCamera = (name, source) =>
  api.post("/camera/add", { name, source }).then((r) => r.data);

export const startCamera = (cameraId) =>
  api.post(`/camera/start?camera_id=${cameraId}`).then((r) => r.data);

export const stopCamera = (cameraId) =>
  api.post(`/camera/stop?camera_id=${cameraId}`).then((r) => r.data);

export const registerFace = (name, files = [], extra = {}) => {
  const form = new FormData();
  form.append("name", name);
  if (extra.company) form.append("company", extra.company);
  if (extra.branch) form.append("branch", extra.branch);
  if (extra.role) form.append("role", extra.role);
  (files || []).forEach((f) => form.append("files", f));
  return api.post("/register-face", form).then((r) => r.data);
};

export const checkKnownFaceName = (name) =>
  api.get(`/known-faces/check-name?name=${encodeURIComponent(name || "")}`).then((r) => r.data);

export const deleteFace = (faceId) =>
  api.delete(`/known-faces/${faceId}`).then((r) => r.data);

export const updateKnownFace = (faceId, data, files = [], keepPhotoIds = null) => {
  const form = new FormData();
  form.append("name", data.name);
  form.append("company", data.company);
  form.append("branch", data.branch);
  form.append("role", data.role);
  if (keepPhotoIds !== null && keepPhotoIds !== undefined) {
    form.append("keep_photo_ids", Array.isArray(keepPhotoIds) ? keepPhotoIds.join(",") : keepPhotoIds);
  }
  files.forEach((f) => form.append("files", f));
  return api.put(`/known-faces/${faceId}`, form).then((r) => r.data);
};
export const updatePerson = updateKnownFace;

// Additional Unknowns Management: moves a known person back into the
// Unknown pool (Additional Unknowns list) instead of hard-deleting them —
// history/photos are preserved, and they'll be auto-matched back into the
// same identity if seen again on camera.
export const revertFaceToUnknown = (faceId) =>
  api.post(`/known-faces/${faceId}/revert-to-unknown`).then((r) => r.data);
export const saveZone = (cameraId, points) =>
  api.post("/zones", { camera_id: cameraId, points }).then((r) => r.data);

export const deleteZone = (cameraId) =>
  api.delete(`/zones/${cameraId}`).then((r) => r.data);

// --- Known/Unknown identification workflow ---
export const confirmKnownPerson = (eventId, knownFaceId) =>
  api.post(`/events/${eventId}/confirm-known`, { known_face_id: knownFaceId }).then((r) => r.data);

// --- Unknown Persons dashboard (dedicated per-identity folders) ---
export const getUnknownPersons = (status = "all") =>
  api.get("/unknown-persons", { params: { status } }).then((r) => r.data);
export const getUnknownPersonSightings = (unknownPersonId) =>
  api.get(`/unknown-persons/${unknownPersonId}/sightings`).then((r) => r.data);
export const convertUnknownToKnown = (unknownPersonId, nameOrPayload) => {
  const payload =
    typeof nameOrPayload === "object"
      ? nameOrPayload
      : { name: nameOrPayload };
  return api
    .post(`/unknown-persons/${unknownPersonId}/convert-to-known`, payload)
    .then((r) => r.data);
};
export const promoteUnknownFace = (unknownId, payload) =>
  api.post(`/alerts/unknown-faces/${unknownId}/promote`, payload).then((r) => r.data);
export const getUnknownFaceDetail = (unknownId) =>
  api.get(`/alerts/unknown-faces/${unknownId}`).then((r) => r.data);
export const deleteUnknownPerson = (unknownPersonId) =>
  api.delete(`/unknown-persons/${unknownPersonId}`).then((r) => r.data);
export const removeSightingFromUnknown = (unknownPersonId, sightingId) =>
  api
    .post(`/unknown-persons/${unknownPersonId}/sightings/${sightingId}/remove`)
    .then((r) => r.data);

// --- Known person profile: view / add / delete / set-cover photos / remove-to-unknown ---
export const getFacePhotos = (faceId) => api.get(`/known-faces/${faceId}/photos`).then((r) => r.data);
export const addFacePhoto = (faceId, file) => {
  const form = new FormData();
  form.append("file", file);
  return api.post(`/known-faces/${faceId}/photos`, form).then((r) => r.data);
};
export const deleteFacePhoto = (faceId, embeddingId) =>
  api.delete(`/known-faces/${faceId}/photos/${embeddingId}`).then((r) => r.data);
export const removeFacePhotoToUnknown = (embeddingId) =>
  api.post(`/known-faces/photos/${embeddingId}/remove-to-unknown`).then((r) => r.data);
export const setCoverPhoto = (faceId, embeddingId) =>
  api.put(`/known-faces/${faceId}/cover/${embeddingId}`).then((r) => r.data);

// --- Telegram Alerts ---
export const getTelegramStatus = () => api.get("/telegram/status").then((r) => r.data);
export const sendTelegramTest = (message) => api.post("/send-telegram", { message }).then((r) => r.data);
export const resendTelegramAlert = (snapshot, caption) => api.post("/resend-telegram-alert", { snapshot, caption }).then((r) => r.data);

// --- Helpers ---
// snapshot_path from the backend can be either flat ("data/snapshots/foo.jpg")
// or nested inside a per-person folder ("data/snapshots/unknown/Unknown-017/foo.jpg").
// The static mount serves everything under data/snapshots/, so we must keep
// the FULL relative path after "data/snapshots/", not just the filename.
export const snapshotUrl = (path) => {
  if (!path) return null;
  const normalized = path.replace(/\\/g, "/");
  const marker = "data/snapshots/";
  const markerIndex = normalized.indexOf(marker);
  const relative =
    markerIndex >= 0 ? normalized.slice(markerIndex + marker.length) : normalized.split("/").pop();
  const encodedPath = relative
    .split("/")
    .filter(Boolean)
    .map(encodeURIComponent)
    .join("/");
  return `${API_BASE}/snapshots/${encodedPath}`;
};

export const videoFeedUrl = (cameraId) => {
  const token = localStorage.getItem("cctv_token") || "";
  return `${API_BASE}/video_feed/${cameraId}?token=${encodeURIComponent(token)}`;
};

export { API_BASE };
