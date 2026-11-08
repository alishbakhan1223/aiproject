import { useState, useEffect, useRef, useMemo, useCallback } from "react";
import { Link } from "react-router-dom";
import { snapshotUrl, promoteUnknownFace, convertUnknownToKnown, getUnknownFaceDetail, getKnownFaces } from "../api";

export default function FaceDetailModal({
  alert,
  onClose,
  onPromoted,
}) {
  const [detailData, setDetailData] = useState(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [showPromoteForm, setShowPromoteForm] = useState(false);
  const [knownFaces, setKnownFaces] = useState([]);
  const [selectedPersonId, setSelectedPersonId] = useState("");
  const [newName, setNewName] = useState("");
  const [company, setCompany] = useState("");
  const [branch, setBranch] = useState("");
  const [role, setRole] = useState("");

  const loadKnownFaces = useCallback(async () => {
    try {
      const faces = await getKnownFaces();
      const sorted = [...faces].sort((a, b) =>
        a.name.localeCompare(b.name, undefined, { sensitivity: "base" })
      );
      setKnownFaces(sorted);
    } catch {
      setKnownFaces([]);
    }
  }, []);

  useEffect(() => {
    loadKnownFaces();
  }, [loadKnownFaces]);

  const selectedPerson = useMemo(() => {
    if (!selectedPersonId || selectedPersonId === "__new__") return null;
    return knownFaces.find((kf) => String(kf.id) === String(selectedPersonId)) || null;
  }, [selectedPersonId, knownFaces]);

  const existingDuplicate = useMemo(() => {
    if (selectedPersonId !== "__new__" || !newName.trim()) return null;
    const trimmed = newName.trim().toLowerCase();
    return knownFaces.find((kf) => kf.name.toLowerCase() === trimmed) || null;
  }, [selectedPersonId, newName, knownFaces]);
  const [submitting, setSubmitting] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");
  const [statusType, setStatusType] = useState(""); // "success" | "error" | "info"
  const [activeSnapshotUrl, setActiveSnapshotUrl] = useState(null);
  const [activeBbox, setActiveBbox] = useState(null);

  const sceneImgRef = useRef(null);
  const [naturalDimensions, setNaturalDimensions] = useState({ width: 0, height: 0 });

  // Escape key handler
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  // Helper to parse bbox
  const parseBbox = (b) => {
    if (!b) return null;
    if (Array.isArray(b)) return b;
    if (typeof b === "string") {
      try {
        const parsed = JSON.parse(b);
        if (Array.isArray(parsed)) return parsed;
      } catch {
        const parts = b.split(",").map((p) => parseFloat(p.trim())).filter((n) => !isNaN(n));
        if (parts.length === 4) return parts;
      }
    }
    return null;
  };

  // Fetch full detail when alert/event is selected
  useEffect(() => {
    if (!alert) return;
    setLoadingDetail(true);
    setStatusMessage("");
    setShowPromoteForm(false);
    setSelectedPersonId("");
    setNewName("");

    const initialScene =
      alert.scene_image_url ||
      alert.raw_snapshot_path ||
      alert.scene_snapshot_path ||
      alert.snapshot_path ||
      alert.face_image_url ||
      alert.face_crop_path;

    const initialFace =
      alert.face_image_url ||
      alert.face_crop_path ||
      alert.snapshot_path ||
      alert.representative_snapshot_path;

    setActiveSnapshotUrl(initialScene || initialFace);
    setActiveBbox(parseBbox(alert.bounding_box));

    const isUnknown = alert.is_unknown || alert.event_type === "unknown_person";
    const rawUnknownId = alert.raw_unknown_id || alert.unknown_person_id || (isUnknown ? alert.unknown_id : null);

    if (isUnknown && rawUnknownId) {
      getUnknownFaceDetail(rawUnknownId)
        .then((data) => {
          setDetailData(data);
          if (data.scene_image_url) {
            setActiveSnapshotUrl(data.scene_image_url);
          }
          if (data.bounding_box) {
            setActiveBbox(parseBbox(data.bounding_box));
          }
        })
        .catch(() => {
          setDetailData(alert);
        })
        .finally(() => {
          setLoadingDetail(false);
        });
    } else {
      setDetailData(alert);
      setLoadingDetail(false);
    }
  }, [alert]);

  if (!alert) return null;

  const currentData = detailData || alert;
  const isUnknown = currentData.is_unknown || currentData.event_type === "unknown_person" || (!currentData.event_type && currentData.unknown_id);
  const isKnown = currentData.event_type === "known_person" || (!isUnknown && currentData.person_name && currentData.event_type !== "weapon_detected" && currentData.event_type !== "restricted_object");

  const displayName =
    currentData.person_name ||
    currentData.unknown_id ||
    (currentData.unknown_person_id ? `Unknown-${String(currentData.unknown_person_id).padStart(3, "0")}` : `Person #${currentData.id || 1}`);

  const rawId = currentData.raw_unknown_id || currentData.unknown_person_id || alert.raw_unknown_id || alert.unknown_person_id;
  const confRaw = currentData.confidence_percent ?? (currentData.confidence != null ? currentData.confidence : 0.85);
  const confPct = typeof confRaw === "number" ? (confRaw <= 1.0 ? Math.round(confRaw * 100) : Math.round(confRaw)) : 85;
  const isInside = (currentData.zone || (currentData.in_zone !== false ? "inside" : "outside"))?.toLowerCase() === "inside";
  const cameraCode = currentData.camera_code || currentData.camera_name || "Camera 1";
  const detectionTime = currentData.timestamp ? new Date(currentData.timestamp).toLocaleString() : "Just now";
  const faceCropUrl = currentData.face_image_url || currentData.face_crop_path || currentData.snapshot_path || currentData.representative_snapshot_path;

  // Handle Promote to Known submission
  const handlePromote = async (e) => {
    e.preventDefault();
    if (!selectedPersonId) return;
    if (selectedPersonId === "__new__" && !newName.trim()) return;

    setSubmitting(true);
    setStatusMessage("Promoting identity to known face database...");
    setStatusType("info");

    try {
      let targetName = "";
      let payload = {};
      if (selectedPersonId === "__new__") {
        targetName = newName.trim();
        payload = {
          name: targetName,
          company: company.trim() || undefined,
          branch: branch.trim() || undefined,
          role: role.trim() || undefined,
        };
      } else {
        const kf = knownFaces.find((f) => String(f.id) === String(selectedPersonId));
        if (!kf) return;
        targetName = kf.name;
        payload = {
          known_face_id: kf.id,
          name: kf.name,
        };
      }

      let result;
      try {
        result = await promoteUnknownFace(rawId || displayName, payload);
      } catch {
        result = await convertUnknownToKnown(rawId, payload);
      }

      setStatusMessage(`✅ Mapped to ${result.name || targetName}`);
      setStatusType("success");
      await loadKnownFaces();

      setTimeout(() => {
        if (onPromoted) onPromoted(result);
        onClose();
      }, 1200);
    } catch (err) {
      setStatusMessage(`❌ ${err.response?.data?.detail || err.message || "Failed to promote identity"}`);
      setStatusType("error");
    } finally {
      setSubmitting(false);
    }
  };

  // Compute Bounding Box CSS Coordinates relative to rendered image
  const renderBoundingBoxOverlay = () => {
    if (!activeBbox || activeBbox.length < 4 || !naturalDimensions.width || !naturalDimensions.height) {
      return null;
    }

    const [bx1, by1, bx2, by2] = activeBbox;
    const nw = naturalDimensions.width;
    const nh = naturalDimensions.height;

    const leftPct = (bx1 / nw) * 100;
    const topPct = (by1 / nh) * 100;
    const widthPct = ((bx2 - bx1) / nw) * 100;
    const heightPct = ((by2 - by1) / nh) * 100;

    return (
      <div
        className="absolute border-2 border-cyan-400 bg-cyan-500/20 shadow-[0_0_15px_rgba(6,182,212,0.6)] rounded-sm pointer-events-none transition-all duration-300"
        style={{
          left: `${leftPct}%`,
          top: `${topPct}%`,
          width: `${widthPct}%`,
          height: `${heightPct}%`,
        }}
      >
        {/* Label Tag on Top of Bounding Box */}
        <div className="absolute -top-6 left-0 bg-cyan-600 text-black font-extrabold text-[10px] px-1.5 py-0.5 rounded shadow whitespace-nowrap flex items-center gap-1">
          <span>🎯</span>
          <span>{displayName} [{confPct}%]</span>
        </div>
        {/* Target Crosshair Corners */}
        <div className="absolute -top-1 -left-1 w-2 h-2 border-t-2 border-l-2 border-white"></div>
        <div className="absolute -top-1 -right-1 w-2 h-2 border-t-2 border-r-2 border-white"></div>
        <div className="absolute -bottom-1 -left-1 w-2 h-2 border-b-2 border-l-2 border-white"></div>
        <div className="absolute -bottom-1 -right-1 w-2 h-2 border-b-2 border-r-2 border-white"></div>
      </div>
    );
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-black/85 backdrop-blur-md flex items-center justify-center p-3 sm:p-6 overflow-y-auto animate-fadeIn"
      onClick={onClose}
    >
      <div
        className="relative max-w-5xl w-full bg-gray-900 border border-gray-700/80 rounded-2xl shadow-2xl overflow-hidden my-auto flex flex-col max-h-[92vh]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Top Bar */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800 bg-gray-950/80">
          <div className="flex items-center gap-3">
            <div
              className={`p-2 rounded-lg border text-lg ${
                isUnknown
                  ? "bg-red-950/60 border-red-800/80 text-red-400"
                  : "bg-emerald-950/60 border-emerald-800/80 text-emerald-400"
              }`}
            >
              {isUnknown ? "🚨" : "👤"}
            </div>
            <div>
              <h2 className="text-base sm:text-lg font-bold text-white flex items-center gap-2">
                <span>Face Detail View</span>
                <span
                  className={`text-xs px-2 py-0.5 rounded font-mono font-semibold border ${
                    isUnknown
                      ? "bg-red-900/60 text-red-300 border-red-700"
                      : "bg-emerald-900/60 text-emerald-300 border-emerald-700"
                  }`}
                >
                  {displayName}
                </span>
              </h2>
              <p className="text-xs text-gray-400">
                Camera Security Event & Identity Analysis
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white p-2 rounded-lg bg-gray-800/80 hover:bg-gray-700 transition"
            title="Close (Esc)"
          >
            ✕
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 overflow-y-auto space-y-6 flex-1">
          {/* Top Section: CNIC-Style Identity Card + Full Scene Snapshot */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* Left Col: CNIC / Passport Card View (5 Cols) */}
            <div className="lg:col-span-5 flex flex-col">
              <div className="h-full bg-gradient-to-b from-gray-900 via-gray-950 to-gray-950 border-2 border-gray-700 rounded-xl p-5 shadow-xl relative overflow-hidden flex flex-col justify-between">
                {/* Official CNIC Card Header */}
                <div className="border-b border-gray-800 pb-3 mb-4">
                  <div className="flex items-center justify-between text-[10px] tracking-wider text-gray-400 uppercase font-semibold">
                    <span className="flex items-center gap-1 text-blue-400">
                      <span>🏛️</span> CCTV SURVEILLANCE SYSTEM
                    </span>
                    <span
                      className={`font-mono font-bold ${
                        isUnknown ? "text-red-400" : "text-emerald-400"
                      }`}
                    >
                      {isUnknown ? "UNIDENTIFIED" : "VERIFIED IDENTITY"}
                    </span>
                  </div>
                  <div className="text-xs font-bold text-gray-200 mt-0.5">
                    SECURITY IDENTIFICATION PROFILE
                  </div>
                </div>

                {/* Passport / CNIC Photo Frame */}
                <div className="flex flex-col items-center justify-center my-2">
                  <div className="relative group">
                    <div className="w-40 h-48 sm:w-44 sm:h-52 bg-black rounded-lg border-2 border-gray-500/80 p-1.5 shadow-[0_0_20px_rgba(0,0,0,0.8)] overflow-hidden flex items-center justify-center relative">
                      {faceCropUrl ? (
                        <img
                          src={snapshotUrl(faceCropUrl)}
                          alt={displayName}
                          className="w-full h-full object-cover rounded"
                        />
                      ) : (
                        <div className="text-gray-600 text-xs flex flex-col items-center gap-1">
                          <span className="text-2xl">👤</span>
                          <span>No Face Crop</span>
                        </div>
                      )}
                      {/* Photo watermark stamp effect */}
                      <div className="absolute bottom-2 right-2 text-[9px] font-mono text-white/50 bg-black/60 px-1 rounded">
                        CCTV CROP
                      </div>
                    </div>
                    {/* Badge Pill */}
                    <div
                      className={`absolute -bottom-3 left-1/2 -translate-x-1/2 text-white text-[11px] font-bold px-3 py-0.5 rounded-full shadow-md whitespace-nowrap border ${
                        isUnknown
                          ? "bg-red-600 border-red-400"
                          : "bg-emerald-600 border-emerald-400"
                      }`}
                    >
                      {displayName}
                    </div>
                  </div>
                </div>

                {/* Card Fields Grid */}
                <div className="mt-6 space-y-2.5 text-xs bg-gray-900/90 rounded-lg p-3.5 border border-gray-800">
                  <div className="flex justify-between border-b border-gray-800/60 pb-1.5">
                    <span className="text-gray-400">Camera:</span>
                    <span className="font-semibold text-gray-200 flex items-center gap-1">
                      <span>📷</span> {cameraCode}
                    </span>
                  </div>

                  <div className="flex justify-between border-b border-gray-800/60 pb-1.5">
                    <span className="text-gray-400">Security Zone:</span>
                    <span
                      className={`font-semibold px-2 py-0.5 rounded text-[11px] ${
                        isInside
                          ? "bg-blue-950 text-blue-300 border border-blue-800"
                          : "bg-gray-800 text-gray-400 border border-gray-700"
                      }`}
                    >
                      {isInside ? "🛡️ Inside Zone" : "🌐 Outside Zone"}
                    </span>
                  </div>

                  <div className="flex justify-between border-b border-gray-800/60 pb-1.5">
                    <span className="text-gray-400">Confidence Score:</span>
                    <span
                      className={`font-bold px-2 py-0.5 rounded text-[11px] ${
                        confPct >= 75
                          ? "bg-emerald-950 text-emerald-300 border border-emerald-800"
                          : confPct >= 50
                          ? "bg-amber-950 text-amber-300 border border-amber-800"
                          : "bg-rose-950 text-rose-300 border border-rose-800"
                      }`}
                    >
                      {confPct}% {confPct >= 75 ? "High" : confPct >= 50 ? "Moderate" : "Low"}
                    </span>
                  </div>

                  <div className="flex justify-between border-b border-gray-800/60 pb-1.5">
                    <span className="text-gray-400">Detection Time:</span>
                    <span className="text-gray-300 font-mono text-[11px]">
                      {detectionTime}
                    </span>
                  </div>

                  {currentData.detection_count > 1 && (
                    <div className="flex justify-between text-gray-400 pt-0.5">
                      <span>Total Sightings:</span>
                      <span className="text-blue-400 font-bold">{currentData.detection_count} times</span>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Right Col: Full Scene Snapshot with Highlighted Box (7 Cols) */}
            <div className="lg:col-span-7 flex flex-col space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-bold uppercase tracking-wider text-gray-400 flex items-center gap-1.5">
                  <span>🎥</span> Full Scene Snapshot (Target Highlighted)
                </h3>
                {activeBbox && (
                  <span className="text-[11px] text-cyan-400 font-mono bg-cyan-950/60 border border-cyan-800/60 px-2 py-0.5 rounded">
                    Box: [{activeBbox.map(Math.round).join(", ")}]
                  </span>
                )}
              </div>

              {/* Snapshot Viewport with Overlay */}
              <div className="relative w-full bg-black rounded-xl border border-gray-700/80 overflow-hidden shadow-2xl flex items-center justify-center min-h-[320px] max-h-[420px]">
                {activeSnapshotUrl ? (
                  <div className="relative inline-block max-w-full max-h-[420px]">
                    <img
                      ref={sceneImgRef}
                      src={snapshotUrl(activeSnapshotUrl)}
                      alt="Full Scene Snapshot"
                      className="max-h-[410px] max-w-full object-contain rounded block"
                      onLoad={(e) => {
                        setNaturalDimensions({
                          width: e.target.naturalWidth,
                          height: e.target.naturalHeight,
                        });
                      }}
                      onError={(e) => {
                        e.target.onerror = null;
                        if (faceCropUrl) {
                          e.target.src = snapshotUrl(faceCropUrl);
                        }
                      }}
                    />
                    {renderBoundingBoxOverlay()}
                  </div>
                ) : (
                  <div className="text-gray-500 text-xs py-16 flex flex-col items-center gap-1">
                    <span>📷</span>
                    <span>No scene snapshot available</span>
                  </div>
                )}
              </div>

              {/* Sighting Thumbnails Strip if multi-sighting */}
              {currentData.sightings && currentData.sightings.length > 1 && (
                <div className="space-y-1.5">
                  <span className="text-[11px] text-gray-400">
                    Sighting History Gallery ({currentData.sightings.length}):
                  </span>
                  <div className="flex gap-2 overflow-x-auto pb-1 max-h-20">
                    {currentData.sightings.map((s, sIdx) => (
                      <div
                        key={s.id || sIdx}
                        onClick={() => {
                          if (s.scene_image_url) setActiveSnapshotUrl(s.scene_image_url);
                          else if (s.face_image_url) setActiveSnapshotUrl(s.face_image_url);
                          if (s.bounding_box) setActiveBbox(parseBbox(s.bounding_box));
                        }}
                        className={`w-16 h-16 rounded-lg bg-black border cursor-pointer overflow-hidden shrink-0 transition ${
                          activeSnapshotUrl === s.scene_image_url || activeSnapshotUrl === s.face_image_url
                            ? "border-cyan-400 ring-2 ring-cyan-500/50"
                            : "border-gray-700 hover:border-gray-500"
                        }`}
                        title={`${s.camera_code} at ${new Date(s.timestamp).toLocaleTimeString()}`}
                      >
                        <img
                          src={snapshotUrl(s.face_image_url || s.scene_image_url || s.snapshot_path)}
                          alt="sighting"
                          className="w-full h-full object-cover"
                        />
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Status Message Alert Banner */}
          {statusMessage && (
            <div
              className={`p-3.5 rounded-xl border text-xs sm:text-sm font-medium transition ${
                statusType === "success"
                  ? "bg-emerald-950/80 text-emerald-300 border-emerald-700"
                  : statusType === "error"
                  ? "bg-rose-950/80 text-rose-300 border-rose-700"
                  : "bg-blue-950/80 text-blue-300 border-blue-700"
              }`}
            >
              {statusMessage}
            </div>
          )}

          {/* Bottom Action Area: Promote to Known Workflow (if Unknown) */}
          <div className="border-t border-gray-800 pt-5">
            {isUnknown ? (
              !showPromoteForm ? (
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="text-xs text-gray-400">
                    <span>Take action on this unknown identity:</span>
                    <p className="text-gray-500 text-[11px]">
                      Promoting registers this unknown face into the Known Face database.
                    </p>
                  </div>
                  <div className="flex items-center gap-3">
                    <button
                      onClick={() => setShowPromoteForm(true)}
                      className="bg-blue-600 hover:bg-blue-500 active:bg-blue-700 text-white font-semibold text-xs sm:text-sm px-5 py-2.5 rounded-xl shadow-lg shadow-blue-600/30 transition flex items-center gap-2"
                    >
                      <span>✓</span>
                      <span>Promote to Known</span>
                    </button>
                    <button
                      onClick={onClose}
                      className="bg-gray-800 hover:bg-gray-700 text-gray-300 text-xs sm:text-sm px-4 py-2.5 rounded-xl transition"
                    >
                      Close
                    </button>
                  </div>
                </div>
              ) : (
                <form onSubmit={handlePromote} className="bg-gray-950/80 border border-gray-800 rounded-xl p-4 space-y-4">
                  <div className="flex items-center justify-between border-b border-gray-800 pb-2">
                    <h4 className="text-sm font-bold text-white flex items-center gap-2">
                      <span>👤</span> Register Person as Known Face
                    </h4>
                    <button
                      type="button"
                      onClick={() => setShowPromoteForm(false)}
                      className="text-xs text-gray-400 hover:text-white"
                    >
                      Cancel
                    </button>
                  </div>

                  <div className="space-y-3">
                    <div>
                      <label className="text-xs text-gray-300 font-medium block mb-1">
                        Map to Known Person <span className="text-red-400">*</span>
                      </label>
                      <select
                        value={selectedPersonId}
                        disabled={submitting || knownFaces.length === 0}
                        onChange={(e) => setSelectedPersonId(e.target.value)}
                        className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-xs sm:text-sm text-white focus:outline-none focus:border-blue-500"
                      >
                        <option value="">
                          {knownFaces.length === 0
                            ? "No known people registered yet"
                            : "Select a known person"}
                        </option>
                        {knownFaces.map((kf) => {
                          const count = kf.photo_count ?? 0;
                          const label =
                            count >= 4
                              ? `${kf.name} (${count}/4 photos, oldest photo will be replaced)`
                              : `${kf.name} (${count}/4 photos)`;
                          return (
                            <option key={kf.id} value={kf.id}>
                              {label}
                            </option>
                          );
                        })}
                      </select>

                      {selectedPerson && (
                        <p className="text-xs mt-1 text-gray-400">
                          {selectedPerson.photo_count >= 4 ? (
                            <span className="text-red-400 font-medium">
                              Note: This person already has 4/4 photos. Mapping will replace their oldest photo.
                            </span>
                          ) : (
                            <span>Photo will be added to this person's profile ({selectedPerson.photo_count || 0}/4 photos).</span>
                          )}
                        </p>
                      )}

                      {/* Info notice */}
                      <div className="mt-2 rounded-lg border border-blue-500/30 bg-blue-950/30 p-2.5 text-xs text-blue-200 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                        <span>
                          Is this a new person? Register them first on the Known People page, then return here and map this unknown to them.
                        </span>
                        <Link
                          to="/persons"
                          className="self-start sm:self-auto bg-blue-600 hover:bg-blue-500 text-white rounded px-2.5 py-1 text-xs font-medium whitespace-nowrap"
                        >
                          Go to Known People
                        </Link>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center justify-end gap-3 pt-2">
                    <button
                      type="button"
                      onClick={() => setShowPromoteForm(false)}
                      disabled={submitting}
                      className="bg-gray-800 hover:bg-gray-700 text-xs px-4 py-2 rounded-lg text-gray-300"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={submitting || !selectedPersonId}
                      className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-semibold text-xs px-5 py-2 rounded-lg shadow-md transition flex items-center gap-1.5"
                    >
                      {submitting ? (
                        <>
                          <span className="animate-spin">🔄</span>
                          <span>Saving...</span>
                        </>
                      ) : (
                        <>
                          <span>✓</span>
                          <span>Confirm Promotion</span>
                        </>
                      )}
                    </button>
                  </div>
                </form>
              )
            ) : (
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-xs text-emerald-400">
                  <span>✅</span>
                  <span>Registered Known Person</span>
                </div>
                <button
                  onClick={onClose}
                  className="bg-gray-800 hover:bg-gray-700 text-gray-300 text-xs px-4 py-2 rounded-xl transition"
                >
                  Close
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
