import { useEffect, useState, useCallback, useMemo } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import {
  getUnknownPersons,
  getUnknownPersonSightings,
  convertUnknownToKnown,
  deleteUnknownPerson,
  snapshotUrl,
  getKnownFaces,
} from "../api";

function unknownLabel(id) {
  return `Unknown-${String(id).padStart(3, "0")}`;
}

function getDaysLeft(p) {
  if (p?.mapping_days_left !== undefined && p?.mapping_days_left !== null) {
    return p.mapping_days_left;
  }
  if (!p?.first_seen) return 30;
  const elapsed = (new Date() - new Date(p.first_seen)) / (1000 * 86400);
  return Math.max(0, Math.floor(30 - elapsed));
}

function ConvertForm({ personId, daysLeft, onDone }) {
  const { isAdmin } = useAuth();
  const [knownFaces, setKnownFaces] = useState([]);
  const [selectedPersonId, setSelectedPersonId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const isExpired = daysLeft <= 0;

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
    if (!selectedPersonId) return null;
    return knownFaces.find((kf) => String(kf.id) === String(selectedPersonId)) || null;
  }, [selectedPersonId, knownFaces]);

  const submit = async (e) => {
    e.preventDefault();
    if (!selectedPersonId) return;
    if (isExpired) {
      setError("Mapping window (30 days) expired. Changes are not allowed anymore.");
      return;
    }
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      const kf = knownFaces.find((f) => String(f.id) === String(selectedPersonId));
      if (!kf) return;
      const payload = { known_face_id: kf.id, name: kf.name };

      const result = await convertUnknownToKnown(personId, payload);
      setSuccess(`Mapped to ${result.name || kf.name}`);
      setSelectedPersonId("");
      await loadKnownFaces();
      onDone?.();
    } catch (err) {
      setError(err.response?.data?.detail || "Conversion failed");
      setBusy(false);
    }
  };

  const handleDelete = async () => {
    if (!isAdmin) return;
    if (!window.confirm(`Delete Unknown-${String(personId).padStart(3, "0")} and all sightings?`)) return;
    setBusy(true);
    setError("");
    try {
      await deleteUnknownPerson(personId);
      onDone?.();
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to delete");
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-2 mt-2">
      <div className="flex flex-wrap items-center gap-2">
        <select
          value={selectedPersonId}
          disabled={busy || isExpired || knownFaces.length === 0}
          onChange={(e) => setSelectedPersonId(e.target.value)}
          className="bg-gray-800 border border-gray-700 rounded px-2.5 py-1 text-xs text-white focus:outline-none focus:border-blue-500"
        >
          <option value="">
            {knownFaces.length === 0 ? "No known people registered yet" : "Select a known person"}
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

        <button
          disabled={busy || isExpired || !selectedPersonId}
          className={`rounded px-3 py-1 text-xs whitespace-nowrap transition ${
            isExpired || !selectedPersonId
              ? "bg-gray-800 text-gray-500 cursor-not-allowed border border-gray-700"
              : "bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white"
          }`}
          title={isExpired ? "Mapping window expired" : !selectedPersonId ? "Select a known person first" : "Mark as Known"}
        >
          Mark as Known
        </button>

        {isAdmin && (
          <button
            type="button"
            disabled={busy}
            onClick={handleDelete}
            className="bg-red-700 hover:bg-red-600 disabled:opacity-50 rounded px-3 py-1 text-xs whitespace-nowrap text-white ml-auto"
            title="Delete unknown person (Admin only)"
          >
            Delete
          </button>
        )}
      </div>

      {selectedPerson && (
        <p className="text-[11px] text-gray-400">
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
      <div className="rounded border border-blue-500/30 bg-blue-950/30 p-2 text-[11px] text-blue-200 flex items-center justify-between gap-2">
        <span>
          Is this a new person? Register them first on the Known People page, then return here and map this unknown to them.
        </span>
        <Link
          to="/persons"
          className="bg-blue-600 hover:bg-blue-500 text-white rounded px-2 py-0.5 text-[11px] font-medium whitespace-nowrap"
        >
          Go to Known People
        </Link>
      </div>

      {error && <p className="text-xs text-red-400">{error}</p>}
      {success && <p className="text-xs text-green-400">{success}</p>}
    </form>
  );
}

function SightingsGallery({ personId, onImageClick }) {
  const [sightings, setSightings] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getUnknownPersonSightings(personId)
      .then(setSightings)
      .catch(() => setError("Failed to load sightings"));
  }, [personId]);

  if (error) return <p className="text-xs text-red-400 mt-2">{error}</p>;
  if (sightings === null) return <p className="text-xs text-gray-500 mt-2">Loading sightings...</p>;
  if (sightings.length === 0) return <p className="text-xs text-gray-500 mt-2">No sightings recorded.</p>;

  return (
    <div className="mt-2 flex gap-2 flex-wrap">
      {sightings.map((s) => (
        <div key={s.id} className="text-center cursor-pointer group" onClick={() => onImageClick?.(s)}>
          {s.snapshot_path ? (
            <img
              src={snapshotUrl(s.snapshot_path)}
              alt="sighting"
              className="w-16 h-16 object-cover rounded border border-gray-700 group-hover:border-blue-500 transition"
            />
          ) : (
            <div className="w-16 h-16 rounded bg-gray-800" />
          )}
          <p className="text-[10px] text-gray-500 mt-0.5">{s.camera_name}</p>
          <p className="text-[10px] text-gray-600">
            {s.timestamp ? new Date(s.timestamp).toLocaleTimeString() : ""}
          </p>
        </div>
      ))}
    </div>
  );
}

export default function UnknownPersonsPage() {
  const [persons, setPersons] = useState([]);
  const [expandedId, setExpandedId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [modalImage, setModalImage] = useState(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setPersons(await getUnknownPersons());
    } catch (err) {
      setError("Failed to load unknown persons. Check your connection and try again.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <div className="p-6 space-y-4 max-w-3xl">
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

      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">Unknown Persons</h1>
          <p className="text-sm text-gray-400">
            One entry per distinct unknown individual, de-duplicated across sightings and
            cameras. Primary cover is automatically set to highest-quality snapshot.
          </p>
        </div>
        <button
          onClick={refresh}
          className="text-xs bg-gray-800 hover:bg-gray-700 rounded px-3 py-1.5 whitespace-nowrap"
        >
          Refresh
        </button>
      </header>

      {loading && <p className="text-sm text-gray-500">Loading...</p>}
      {error && <p className="text-sm text-red-400">{error}</p>}
      {!loading && !error && persons.length === 0 && (
        <p className="text-sm text-gray-500">No unknown persons recorded yet.</p>
      )}

      <div className="space-y-3">
        {persons.map((p) => {
          const daysLeft = getDaysLeft(p);
          const isExpiringSoon = daysLeft <= 3;
          const isExpired = daysLeft <= 0;

          return (
            <div key={p.id} className="rounded-xl border border-gray-700 bg-gray-900 p-4">
              <div className="flex items-center gap-4">
                {p.representative_snapshot_path ? (
                  <img
                    src={snapshotUrl(p.representative_snapshot_path)}
                    alt={unknownLabel(p.id)}
                    className="w-16 h-16 object-cover rounded-lg cursor-pointer border border-gray-700 hover:border-blue-500"
                    onClick={() =>
                      setModalImage({
                        url: snapshotUrl(p.representative_snapshot_path),
                        title: unknownLabel(p.id),
                        subtitle: "Primary Snapshot (Highest Quality)",
                      })
                    }
                  />
                ) : (
                  <div className="w-16 h-16 rounded-lg bg-gray-800 flex items-center justify-center text-xs text-gray-500">
                    no photo
                  </div>
                )}

                <div className="flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-mono font-semibold text-sm">{unknownLabel(p.id)}</span>
                    <span className="text-xs bg-red-600/80 rounded px-2 py-0.5">
                      {p.detection_count} detection{p.detection_count === 1 ? "" : "s"}
                    </span>
                    {/* Countdown badge */}
                    <span
                      className={`text-[10px] px-2 py-0.5 rounded font-semibold ${
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
                  <p className="text-xs text-gray-400 mt-1">
                    First seen: {p.first_seen ? new Date(p.first_seen).toLocaleString() : "—"}
                  </p>
                  <p className="text-xs text-gray-400">
                    Last seen: {p.last_seen ? new Date(p.last_seen).toLocaleString() : "—"}
                  </p>
                </div>

                <button
                  onClick={() => setExpandedId(expandedId === p.id ? null : p.id)}
                  className="text-xs bg-gray-800 hover:bg-gray-700 rounded px-3 py-1.5 whitespace-nowrap"
                >
                  {expandedId === p.id ? "Hide details" : "View Details"}
                </button>
              </div>

              <ConvertForm personId={p.id} daysLeft={daysLeft} onDone={refresh} />

              {expandedId === p.id && (
                <SightingsGallery
                  personId={p.id}
                  onImageClick={(s) =>
                    setModalImage({
                      url: snapshotUrl(s.snapshot_path),
                      title: unknownLabel(p.id),
                      subtitle: `${s.camera_name} • ${s.timestamp ? new Date(s.timestamp).toLocaleString() : ""}`,
                    })
                  }
                />
              )}
            </div>
          );
        })}
      </div>

      {modalImage && (
        <div
          className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4"
          onClick={() => setModalImage(null)}
        >
          <div
            className="relative max-w-2xl w-full bg-gray-900 border border-gray-700 rounded-xl p-4 shadow-2xl flex flex-col items-center gap-3"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="w-full flex items-center justify-between text-xs text-gray-400">
              <div>
                <span className="font-semibold text-gray-200">{modalImage.title}</span>
                {modalImage.subtitle && <span className="ml-2 text-gray-400">• {modalImage.subtitle}</span>}
              </div>
              <button
                onClick={() => setModalImage(null)}
                className="text-gray-400 hover:text-white text-base px-2 py-1 rounded bg-gray-800"
              >
                ✕
              </button>
            </div>
            <div className="w-full flex items-center justify-center bg-black/50 rounded-lg overflow-hidden max-h-[60vh]">
              <img src={modalImage.url} alt="Full View" className="max-h-[58vh] max-w-full object-contain rounded" />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
