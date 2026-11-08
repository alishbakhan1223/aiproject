import { useEffect, useState, useCallback, useMemo } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import {
  getUnknownPersons,
  getUnknownPersonSightings,
  convertUnknownToKnown,
  deleteUnknownPerson,
  removeSightingFromUnknown,
  snapshotUrl,
  getKnownFaces,
} from "../api";

function getDaysLeft(p) {
  if (p?.mapping_days_left !== undefined && p?.mapping_days_left !== null) {
    return p.mapping_days_left;
  }
  if (!p?.first_seen) return 30;
  const elapsed = (new Date() - new Date(p.first_seen)) / (1000 * 86400);
  return Math.max(0, Math.floor(30 - elapsed));
}

function ImageModal({ src, title, subtitle, onClose }) {
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  if (!src) return null;

  return (
    <div
      className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="relative max-w-2xl w-full bg-gray-900 border border-gray-700 rounded-xl p-4 shadow-2xl flex flex-col items-center gap-3"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="w-full flex items-center justify-between text-xs text-gray-400">
          <div>
            <span className="font-semibold text-gray-200">{title}</span>
            {subtitle && <span className="ml-2 text-gray-400">• {subtitle}</span>}
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white text-base px-2 py-1 rounded bg-gray-800"
          >
            ✕
          </button>
        </div>
        <div className="w-full flex items-center justify-center bg-black/50 rounded-lg overflow-hidden max-h-[60vh]">
          <img src={src} alt="Snapshot Full View" className="max-h-[58vh] max-w-full object-contain rounded" />
        </div>
      </div>
    </div>
  );
}

export default function UnknownReviewPage() {
  const { isAdmin } = useAuth();
  const [unknownPersons, setUnknownPersons] = useState([]);
  const [selected, setSelected] = useState(null);
  const [sightings, setSightings] = useState([]);
  const [knownFaces, setKnownFaces] = useState([]);
  const [selectedPersonId, setSelectedPersonId] = useState("");
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(false);
  const [removingSightingId, setRemovingSightingId] = useState(null);
  const [modalImage, setModalImage] = useState(null);

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

  const refresh = useCallback(async () => {
    try {
      const data = await getUnknownPersons();
      setUnknownPersons(data);
    } catch {
      setUnknownPersons([]);
    }
  }, []);

  useEffect(() => {
    refresh();
    loadKnownFaces();
    const interval = setInterval(() => {
      refresh();
      loadKnownFaces();
    }, 5000);
    return () => clearInterval(interval);
  }, [refresh, loadKnownFaces]);

  const selectedPerson = useMemo(() => {
    if (!selectedPersonId) return null;
    return knownFaces.find((kf) => String(kf.id) === String(selectedPersonId)) || null;
  }, [selectedPersonId, knownFaces]);

  const selectPerson = async (person) => {
    setSelected(person);
    setSelectedPersonId("");
    setStatus("");
    try {
      const data = await getUnknownPersonSightings(person.id);
      setSightings(data);
    } catch {
      setSightings([]);
    }
  };

  const handleMakeKnown = async () => {
    if (!selected) return;
    if (!selectedPersonId) return;

    const daysLeft = getDaysLeft(selected);
    if (daysLeft <= 0) {
      setStatus("❌ Mapping window (30 days) expired. Changes are not allowed anymore.");
      return;
    }

    const kf = knownFaces.find((f) => String(f.id) === String(selectedPersonId));
    if (!kf) return;

    setLoading(true);
    setStatus("Confirming...");

    try {
      const payload = { known_face_id: kf.id, name: kf.name };
      const result = await convertUnknownToKnown(selected.id, payload);
      setStatus(`✅ Mapped to ${result.name || kf.name}`);
      setSelected(null);
      setSightings([]);
      setSelectedPersonId("");
      await refresh();
      await loadKnownFaces();
    } catch (err) {
      setStatus(`❌ ${err.response?.data?.detail || "Failed to map person"}`);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (personToDelete = selected) => {
    if (!isAdmin) return;
    if (!personToDelete) return;
    const label = `Unknown-${String(personToDelete.id).padStart(3, "0")}`;
    if (!window.confirm(`Delete ${label} and all associated sightings?`)) return;
    setLoading(true);
    setStatus("Deleting...");
    try {
      await deleteUnknownPerson(personToDelete.id);
      setStatus(`✅ Deleted ${label}`);
      if (selected?.id === personToDelete.id) {
        setSelected(null);
        setSightings([]);
      }
      await refresh();
    } catch (err) {
      setStatus(`❌ ${err.response?.data?.detail || "Failed to delete"}`);
    } finally {
      setLoading(false);
    }
  };

  const handleRemoveSighting = async (sighting) => {
    if (!selected) return;
    if (
      !window.confirm(
        "Remove this photo from this identity? It'll become its own separate Unknown card — nothing is deleted."
      )
    )
      return;
    setRemovingSightingId(sighting.id);
    setStatus("Splitting into a new identity...");
    try {
      const newPerson = await removeSightingFromUnknown(selected.id, sighting.id);
      setStatus(`✅ Moved to new identity Unknown-${String(newPerson.id).padStart(3, "0")}`);
      await refresh();

      const stillExists = (await getUnknownPersons()).some((p) => p.id === selected.id);
      if (!stillExists) {
        setSelected(null);
        setSightings([]);
      } else {
        setSightings(await getUnknownPersonSightings(selected.id));
      }
    } catch (err) {
      setStatus(`❌ ${err.response?.data?.detail || "Failed to remove sighting"}`);
    } finally {
      setRemovingSightingId(null);
    }
  };

  const selectedDaysLeft = selected ? getDaysLeft(selected) : 30;
  const isSelectedExpired = selectedDaysLeft <= 0;

  return (
    <div className="p-6 space-y-4">
      {/* Rule 2: 30-Day Mapping Window Prominent Banner */}
      <div className="rounded-xl border-2 border-red-500/80 bg-red-950/40 p-4 shadow-lg text-red-200 flex items-start gap-3">
        <span className="text-2xl leading-none select-none text-red-400">⚠️</span>
        <div className="space-y-1">
          <p className="font-extrabold text-lg sm:text-xl text-red-300 leading-snug">
            An unknown person can be mapped within 30 days. After 30 days it cannot be mapped and is permanently removed automatically.
          </p>
          <p className="text-xs text-red-400/80">
            Rule 2 Retention Policy: Unmapped detections are automatically deleted after 30 days. Map identities before their window expires.
          </p>
        </div>
      </div>

      <header>
        <h1 className="text-xl font-bold">Unknown Review</h1>
        <p className="text-sm text-gray-400">
          Each card below is one distinct unidentified person with highest-quality cover selection.
        </p>
      </header>

      <div className="grid grid-cols-3 gap-4">
        {/* Left: distinct unknown identities */}
        <div className="col-span-1 space-y-2 max-h-[70vh] overflow-y-auto pr-1">
          {unknownPersons.map((p) => {
            const daysLeft = getDaysLeft(p);
            const isExpiringSoon = daysLeft <= 3;
            const isExpired = daysLeft <= 0;

            return (
              <div
                key={p.id}
                onClick={() => selectPerson(p)}
                className={`flex gap-3 p-2 rounded-lg cursor-pointer border transition ${
                  selected?.id === p.id
                    ? "border-blue-600 bg-gray-800"
                    : "border-gray-800 bg-gray-900 hover:border-gray-700"
                }`}
              >
                {p.representative_snapshot_path ? (
                  <img
                    src={snapshotUrl(p.representative_snapshot_path)}
                    alt={`Unknown-${p.id}`}
                    className="w-14 h-14 object-cover rounded"
                  />
                ) : (
                  <div className="w-14 h-14 rounded bg-gray-800 flex items-center justify-center text-xs text-gray-500">
                    —
                  </div>
                )}
                <div className="text-xs text-gray-400 flex-1">
                  <div className="text-red-500 font-semibold flex items-center justify-between">
                    <span>Unknown-{String(p.id).padStart(3, "0")}</span>
                  </div>
                  <div>{p.detection_count} sighting(s)</div>
                  <div>Last: {p.last_seen ? new Date(p.last_seen).toLocaleString() : "—"}</div>

                  {/* Mapping countdown badge */}
                  <div className="mt-1">
                    <span
                      className={`inline-block text-[10px] px-1.5 py-0.5 rounded font-semibold ${
                        isExpired
                          ? "bg-red-950 text-red-300 border border-red-700"
                          : isExpiringSoon
                          ? "bg-red-900/80 text-red-200 border border-red-500 font-bold"
                          : "bg-emerald-950 text-emerald-300 border border-emerald-700"
                      }`}
                    >
                      {isExpired ? "Mapping window: Expired" : `Mapping window: ${daysLeft} days left`}
                    </span>
                  </div>
                </div>
              </div>
            );
          })}
          {unknownPersons.length === 0 && (
            <p className="text-sm text-gray-500 p-2">No unidentified people currently on file.</p>
          )}
        </div>

        {/* Right: review panel */}
        <div className="col-span-2">
          {selected ? (
            <div className="rounded-xl border border-gray-700 bg-gray-900 p-4 space-y-4">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="px-2 py-1 rounded text-xs bg-red-600 font-semibold">
                  Unknown-{String(selected.id).padStart(3, "0")}
                </span>
                <span className="text-xs text-gray-400">
                  First seen {selected.first_seen ? new Date(selected.first_seen).toLocaleString() : "—"}
                </span>
                <span
                  className={`ml-auto text-xs px-2 py-0.5 rounded font-semibold ${
                    isSelectedExpired
                      ? "bg-red-900 text-red-200 border border-red-600"
                      : selectedDaysLeft <= 3
                      ? "bg-red-900/80 text-red-200 border border-red-500"
                      : "bg-emerald-900/80 text-emerald-200 border border-emerald-600"
                  }`}
                >
                  {isSelectedExpired ? "Mapping window: Expired" : `Mapping window: ${selectedDaysLeft} days left`}
                </span>
              </div>

              <div className="relative group w-44 h-44 cursor-pointer">
                <img
                  src={snapshotUrl(selected.representative_snapshot_path)}
                  alt="Primary snapshot"
                  className="w-full h-full object-cover rounded-lg border border-gray-700"
                />
                <div
                  className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition rounded-lg flex items-center justify-center text-xs text-white"
                  onClick={() =>
                    setModalImage({
                      url: snapshotUrl(selected.representative_snapshot_path),
                      title: `Unknown-${String(selected.id).padStart(3, "0")}`,
                      subtitle: "Primary Snapshot (Highest Quality)",
                    })
                  }
                >
                  🔍 View Full Photo
                </div>
              </div>

              <div>
                <label className="text-xs text-gray-400 mb-1 block">
                  Sighting history ({sightings.length}) — click any photo to enlarge
                </label>
                <div className="max-h-40 overflow-y-auto space-y-1">
                  {sightings.map((s) => (
                    <div
                      key={s.id}
                      className="flex gap-2 items-center bg-gray-800 rounded px-2 py-1 text-xs text-gray-400"
                    >
                      {s.snapshot_path && (
                        <img
                          src={snapshotUrl(s.snapshot_path)}
                          alt="sighting thumbnail"
                          className="w-8 h-8 object-cover rounded cursor-pointer hover:ring-2 hover:ring-blue-500"
                          onClick={() =>
                            setModalImage({
                              url: snapshotUrl(s.snapshot_path),
                              title: `Unknown-${String(selected.id).padStart(3, "0")}`,
                              subtitle: `${s.camera_name} • ${s.timestamp ? new Date(s.timestamp).toLocaleString() : ""}`,
                            })
                          }
                        />
                      )}
                      <span>{s.camera_name}</span>
                      <span>•</span>
                      <span>{s.timestamp ? new Date(s.timestamp).toLocaleString() : "—"}</span>
                      {s.quality_score !== undefined && s.quality_score !== null && (
                        <span className="text-[10px] text-gray-400 bg-gray-900 rounded px-1.5 py-0.5">
                          Q:{s.quality_score.toFixed(0)}
                        </span>
                      )}
                      <button
                        onClick={() => handleRemoveSighting(s)}
                        disabled={removingSightingId === s.id}
                        className="ml-auto bg-yellow-700 hover:bg-yellow-600 disabled:opacity-40 rounded px-2 py-0.5 text-[10px] whitespace-nowrap"
                        title="Move this photo out into its own separate Unknown identity"
                      >
                        {removingSightingId === s.id ? "Removing..." : "Remove"}
                      </button>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <label className="text-xs text-gray-400 mb-1 block">Map to Known Person</label>
                <select
                  value={selectedPersonId}
                  disabled={isSelectedExpired || loading || knownFaces.length === 0}
                  onChange={(e) => setSelectedPersonId(e.target.value)}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500 disabled:opacity-50"
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
                  <p className="text-xs mt-1.5 text-gray-400">
                    {selectedPerson.photo_count >= 4 ? (
                      <span className="text-red-400 font-medium">
                        Note: This person already has 4/4 photos. Mapping will replace their oldest photo.
                      </span>
                    ) : (
                      <span>Photo will be added to this person's profile ({selectedPerson.photo_count || 0}/4 photos).</span>
                    )}
                  </p>
                )}

                {/* Info Notice: Register new person on Known People page first */}
                <div className="mt-3 rounded-lg border border-blue-500/30 bg-blue-950/30 p-2.5 text-xs text-blue-200 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="text-base select-none text-blue-400">ℹ️</span>
                    <span>
                      Is this a new person? Register them first on the Known People page, then return here and map this unknown to them.
                    </span>
                  </div>
                  <Link
                    to="/persons"
                    className="self-start sm:self-auto bg-blue-600 hover:bg-blue-500 text-white rounded px-3 py-1 text-xs font-medium whitespace-nowrap transition"
                  >
                    Go to Known People
                  </Link>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={handleMakeKnown}
                  disabled={loading || isSelectedExpired || !selectedPersonId}
                  className={`rounded px-4 py-2 text-sm font-medium transition ${
                    isSelectedExpired || !selectedPersonId
                      ? "bg-gray-800 text-gray-500 cursor-not-allowed border border-gray-700"
                      : "bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white"
                  }`}
                  title={
                    isSelectedExpired
                      ? "Mapping window expired"
                      : !selectedPersonId
                      ? "Select a known person first"
                      : "Mark as known person"
                  }
                >
                  ✓ Mark as Known
                </button>
                <button
                  onClick={() => {
                    setSelected(null);
                    setSelectedPersonId("");
                  }}
                  disabled={loading}
                  className="bg-gray-800 hover:bg-gray-700 rounded px-4 py-2 text-sm"
                >
                  Cancel
                </button>
                {isAdmin && (
                  <button
                    type="button"
                    onClick={() => handleDelete(selected)}
                    disabled={loading}
                    className="ml-auto bg-red-600/80 hover:bg-red-600 disabled:opacity-40 text-white rounded px-3.5 py-2 text-sm font-medium flex items-center gap-1.5 transition"
                    title="Delete this unknown person (Admin only)"
                  >
                    🗑️ Delete Unknown
                  </button>
                )}
              </div>
              {status && <p className="text-xs text-gray-400">{status}</p>}
            </div>
          ) : (
            <p className="text-sm text-gray-500">Select an unknown identity on the left to review it.</p>
          )}
        </div>
      </div>

      {modalImage && (
        <ImageModal
          src={modalImage.url}
          title={modalImage.title}
          subtitle={modalImage.subtitle}
          onClose={() => setModalImage(null)}
        />
      )}
    </div>
  );
}
