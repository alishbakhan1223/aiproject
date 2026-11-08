import { useState, useEffect } from "react";
import {
  registerFace,
  updateKnownFace,
  revertFaceToUnknown,
  snapshotUrl,
  getFacePhotos,
  addFacePhoto,
  removeFacePhotoToUnknown,
  setCoverPhoto,
} from "../api";

function formatHoursLeft(hours) {
  if (hours === null || hours === undefined) return null;
  const h = Math.floor(hours);
  const m = Math.floor((hours % 1) * 60);
  return `${h}h ${m}m left`;
}

function PhotoLightboxModal({ photos, initialIndex, onClose, onSetCover, onRemove, busy }) {
  const [currentIndex, setCurrentIndex] = useState(initialIndex);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowLeft") {
        setCurrentIndex((prev) => (prev > 0 ? prev - 1 : photos.length - 1));
      }
      if (e.key === "ArrowRight") {
        setCurrentIndex((prev) => (prev < photos.length - 1 ? prev + 1 : 0));
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [photos.length, onClose]);

  const currentPhoto = photos[currentIndex];
  if (!currentPhoto) return null;

  const isMapped = currentPhoto.source_unknown_id !== null && currentPhoto.source_unknown_id !== undefined;
  const isLocked = currentPhoto.revert_locked;
  const hoursLeftStr = formatHoursLeft(currentPhoto.revert_hours_left);

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
          <div className="flex items-center gap-2 flex-wrap font-medium text-gray-200">
            <span>Photo {currentIndex + 1} of {photos.length}</span>
            {currentPhoto.is_cover && (
              <span className="bg-blue-600 text-white rounded px-1.5 py-0.5 text-[10px]">
                Cover Photo
              </span>
            )}
            {currentPhoto.quality_score !== undefined && currentPhoto.quality_score !== null && (
              <span className="text-gray-400 text-[11px]">
                Quality: {currentPhoto.quality_score.toFixed(1)}
              </span>
            )}
            {isMapped && (
              isLocked ? (
                <span className="bg-red-700 text-white rounded px-2 py-0.5 text-[10px] font-bold">
                  🔒 Locked
                </span>
              ) : (
                <span
                  className={`rounded px-2 py-0.5 text-[10px] font-semibold ${
                    currentPhoto.revert_hours_left <= 12
                      ? "bg-yellow-600/90 text-yellow-100"
                      : "bg-emerald-600/90 text-white"
                  }`}
                >
                  Revert allowed: {hoursLeftStr}
                </span>
              )
            )}
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white text-base px-2 py-1 rounded bg-gray-800"
          >
            ✕
          </button>
        </div>

        <div className="relative w-full flex items-center justify-center bg-black/50 rounded-lg overflow-hidden min-h-[280px] max-h-[60vh]">
          <img
            src={snapshotUrl(currentPhoto.photo_path)}
            alt="Full size view"
            className="max-h-[58vh] max-w-full object-contain rounded"
          />

          {photos.length > 1 && (
            <>
              <button
                onClick={() => setCurrentIndex((prev) => (prev > 0 ? prev - 1 : photos.length - 1))}
                className="absolute left-2 bg-black/60 hover:bg-black/80 text-white rounded-full p-2 text-sm"
                title="Previous photo (←)"
              >
                ◀
              </button>
              <button
                onClick={() => setCurrentIndex((prev) => (prev < photos.length - 1 ? prev + 1 : 0))}
                className="absolute right-2 bg-black/60 hover:bg-black/80 text-white rounded-full p-2 text-sm"
                title="Next photo (→)"
              >
                ▶
              </button>
            </>
          )}
        </div>

        <div className="w-full flex items-center justify-between pt-1 border-t border-gray-800">
          <div className="text-[11px] text-gray-500">
            {currentPhoto.added_at ? new Date(currentPhoto.added_at).toLocaleString() : ""}
          </div>
          <div className="flex items-center gap-2">
            {!currentPhoto.is_cover && (
              <button
                onClick={() => onSetCover(currentPhoto.id)}
                disabled={busy}
                className="text-xs bg-blue-600 hover:bg-blue-500 text-white rounded px-3 py-1 font-medium"
              >
                Set as Cover
              </button>
            )}
            <button
              onClick={() => {
                if (isLocked) return;
                onRemove(currentPhoto.id);
                onClose();
              }}
              disabled={busy || isLocked}
              className={`text-xs rounded px-3 py-1 font-medium ${
                isLocked
                  ? "bg-gray-800 text-gray-500 border border-gray-700 cursor-not-allowed opacity-60"
                  : "bg-yellow-600 hover:bg-yellow-500 text-white"
              }`}
              title={
                isLocked
                  ? "Revert window (48 hours) closed. Changes are not allowed anymore."
                  : "Restore to original Unknown identity"
              }
            >
              {isLocked ? "🔒 Locked" : "Remove to Unknown"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function PersonProfile({ face, onClose, onChanged }) {
  const [photos, setPhotos] = useState(null);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [viewingIndex, setViewingIndex] = useState(null);

  const refreshPhotos = async () => {
    try {
      const data = await getFacePhotos(face.id);
      setPhotos(data);
    } catch {
      setPhotos([]);
    }
  };

  useEffect(() => {
    refreshPhotos();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [face.id]);

  const handleAddPhoto = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setStatus("Adding photo...");
    try {
      await addFacePhoto(face.id, file);
      setStatus("✅ Photo added");
      await refreshPhotos();
      onChanged?.();
    } catch (err) {
      setStatus(`❌ ${err.response?.data?.detail || "Failed to add photo"}`);
    } finally {
      setBusy(false);
      e.target.value = "";
    }
  };

  const handleRemovePhoto = async (embeddingId) => {
    if (!confirm("Move this photo back to its original Unknown identity?")) return;
    setBusy(true);
    setStatus("Restoring photo to Unknown...");
    try {
      const res = await removeFacePhotoToUnknown(embeddingId);
      if (res.restored_to_original === false) {
        setStatus("ℹ️ Restored as new Unknown entry (original id untraceable)");
      } else {
        setStatus(`✅ Restored to ${res.label}`);
      }
      await refreshPhotos();
      onChanged?.();
    } catch (err) {
      setStatus(`❌ ${err.response?.data?.detail || "Failed to remove photo"}`);
    } finally {
      setBusy(false);
    }
  };

  const handleSetCover = async (embeddingId) => {
    setBusy(true);
    try {
      await setCoverPhoto(face.id, embeddingId);
      await refreshPhotos();
      onChanged?.();
    } catch (err) {
      setStatus(`❌ ${err.response?.data?.detail || "Failed to set cover photo"}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-2 bg-gray-950 border border-gray-700 rounded-lg p-3 space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium">{face.name}</p>
          <p className="text-xs text-gray-500">
            {[face.company, face.branch, face.role].filter(Boolean).join(" • ") || "No profile details"}
          </p>
        </div>
        <button onClick={onClose} className="text-xs text-gray-400 hover:text-white">
          Close
        </button>
      </div>

      <div>
        <label className="text-xs text-gray-400 mb-1 block">
          Photos ({photos?.length ?? "…"}/4) — click any photo to open full view
        </label>
        <div className="grid grid-cols-4 gap-2">
          {photos?.map((p, idx) => {
            const isMapped = p.source_unknown_id !== null && p.source_unknown_id !== undefined;
            const isLocked = p.revert_locked;
            const hoursLeftStr = formatHoursLeft(p.revert_hours_left);

            return (
              <div
                key={p.id}
                onClick={() => setViewingIndex(idx)}
                className="relative group cursor-pointer"
              >
                <img
                  src={snapshotUrl(p.photo_path)}
                  alt={`Photo ${idx + 1}`}
                  className={`w-full aspect-square object-cover rounded transition hover:opacity-90 ${
                    p.is_cover ? "ring-2 ring-blue-500" : ""
                  }`}
                />
                {p.is_cover && (
                  <span className="absolute top-1 left-1 text-[10px] bg-blue-600 rounded px-1">
                    Cover
                  </span>
                )}
                {/* 48-Hour Revert Lock Badge */}
                {isMapped && (
                  isLocked ? (
                    <span className="absolute top-1 right-1 text-[9px] bg-red-600/95 text-white rounded px-1 font-bold shadow">
                      🔒 Locked
                    </span>
                  ) : (
                    <span
                      className={`absolute top-1 right-1 text-[9px] rounded px-1 font-semibold shadow ${
                        p.revert_hours_left <= 12
                          ? "bg-yellow-600 text-yellow-100"
                          : "bg-emerald-600 text-white"
                      }`}
                      title={`Revert allowed: ${hoursLeftStr}`}
                    >
                      {Math.floor(p.revert_hours_left)}h left
                    </span>
                  )
                )}
                {p.quality_score !== undefined && p.quality_score !== null && (
                  <span className="absolute bottom-1 left-1 text-[9px] bg-black/70 text-gray-300 rounded px-1">
                    Q:{p.quality_score.toFixed(0)}
                  </span>
                )}
                <div
                  className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition flex flex-col items-center justify-center gap-1 rounded"
                  onClick={(e) => e.stopPropagation()}
                >
                  <button
                    onClick={() => setViewingIndex(idx)}
                    className="text-[10px] bg-gray-700 hover:bg-gray-600 text-white rounded px-2 py-0.5"
                  >
                    🔍 View
                  </button>
                  {!p.is_cover && (
                    <button
                      onClick={() => handleSetCover(p.id)}
                      disabled={busy}
                      className="text-[10px] bg-blue-600 hover:bg-blue-500 rounded px-2 py-0.5"
                    >
                      Set cover
                    </button>
                  )}
                  <button
                    onClick={() => {
                      if (isLocked) return;
                      handleRemovePhoto(p.id);
                    }}
                    disabled={busy || isLocked}
                    className={`text-[10px] rounded px-2 py-0.5 ${
                      isLocked
                        ? "bg-gray-800 text-gray-500 cursor-not-allowed border border-gray-700 opacity-60"
                        : "bg-yellow-600 hover:bg-yellow-500 text-white"
                    }`}
                    title={
                      isLocked
                        ? "Revert window (48 hours) closed. Changes are not allowed anymore."
                        : isMapped
                        ? `Revert allowed: ${hoursLeftStr}`
                        : "Restore this photo back to its original Unknown identity"
                    }
                  >
                    {isLocked ? "🔒 Locked" : "Remove"}
                  </button>
                </div>
              </div>
            );
          })}
          {photos && photos.length < 4 && (
            <label className="w-full aspect-square rounded border border-dashed border-gray-600 flex items-center justify-center text-xs text-gray-500 cursor-pointer hover:border-gray-400">
              + Add
              <input type="file" accept=".jpg,.jpeg,image/jpeg" className="hidden" onChange={handleAddPhoto} />
            </label>
          )}
        </div>
      </div>
      {status && <p className="text-xs text-gray-400">{status}</p>}

      {viewingIndex !== null && photos && (
        <PhotoLightboxModal
          photos={photos}
          initialIndex={viewingIndex}
          onClose={() => setViewingIndex(null)}
          onSetCover={handleSetCover}
          onRemove={handleRemovePhoto}
          busy={busy}
        />
      )}
    </div>
  );
}

function EditPersonModal({ face, onClose, onSaved }) {
  const [name, setName] = useState(face.name || "");
  const [company, setCompany] = useState(face.company || "");
  const [branch, setBranch] = useState(face.branch || "");
  const [role, setRole] = useState(face.role || "");
  const [touched, setTouched] = useState({ name: false, company: false, branch: false, role: false });
  const [submitAttempted, setSubmitAttempted] = useState(false);

  const [existingPhotos, setExistingPhotos] = useState([]);
  const [removedPhotoIds, setRemovedPhotoIds] = useState([]);
  const [newFiles, setNewFiles] = useState([]);
  const [newPreviews, setNewPreviews] = useState([]);
  const [loadingPhotos, setLoadingPhotos] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    getFacePhotos(face.id)
      .then((photos) => {
        if (active) {
          setExistingPhotos(photos || []);
          setLoadingPhotos(false);
        }
      })
      .catch(() => {
        if (active) setLoadingPhotos(false);
      });
    return () => {
      active = false;
    };
  }, [face.id]);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  useEffect(() => {
    const urls = newFiles.map((f) => URL.createObjectURL(f));
    setNewPreviews(urls);
    return () => {
      urls.forEach((u) => URL.revokeObjectURL(u));
    };
  }, [newFiles]);

  const handleAddNewFiles = (e) => {
    const selected = Array.from(e.target.files);
    const nonJpg = selected.filter(
      (f) => !/\.(jpe?g)$/i.test(f.name) && f.type !== "image/jpeg"
    );
    if (nonJpg.length > 0) {
      setError(`Only JPG/JPEG photos are supported. Rejected: ${nonJpg.map((f) => f.name).join(", ")}`);
      return;
    }

    const keptExisting = existingPhotos.filter((p) => !removedPhotoIds.includes(p.id));
    const availableSlots = 4 - (keptExisting.length + newFiles.length);
    if (availableSlots <= 0) {
      setError("Maximum 4 photos allowed");
      return;
    }

    const toAdd = selected.slice(0, availableSlots);
    setNewFiles((prev) => [...prev, ...toAdd]);
    setError("");
    e.target.value = "";
  };

  const handleRemoveExistingPhoto = (photoId) => {
    const keptCount = existingPhotos.filter((p) => !removedPhotoIds.includes(p.id)).length;
    const totalCount = keptCount + newFiles.length;
    if (totalCount <= 1) {
      setError("At least 1 photo is required");
      return;
    }
    setRemovedPhotoIds((prev) => [...prev, photoId]);
    setError("");
  };

  const handleRemoveNewFile = (index) => {
    const keptCount = existingPhotos.filter((p) => !removedPhotoIds.includes(p.id)).length;
    const totalCount = keptCount + newFiles.length;
    if (totalCount <= 1) {
      setError("At least 1 photo is required");
      return;
    }
    setNewFiles((prev) => prev.filter((_, i) => i !== index));
    setError("");
  };

  const keptExistingPhotos = existingPhotos.filter((p) => !removedPhotoIds.includes(p.id));
  const totalPhotos = keptExistingPhotos.length + newFiles.length;

  const trimmedName = name.trim();
  const trimmedCompany = company.trim();
  const trimmedBranch = branch.trim();
  const trimmedRole = role.trim();

  const isNameValid = trimmedName.length > 0;
  const isCompanyValid = trimmedCompany.length > 0;
  const isBranchValid = trimmedBranch.length > 0;
  const isRoleValid = trimmedRole.length > 0;
  const isPhotosCountValid = totalPhotos >= 1 && totalPhotos <= 4;
  const isFormValid = isNameValid && isCompanyValid && isBranchValid && isRoleValid && isPhotosCountValid;

  const handleSave = async (e) => {
    e.preventDefault();
    setSubmitAttempted(true);
    if (!isFormValid) return;

    setSaving(true);
    setError("");
    try {
      const keptIds = keptExistingPhotos.map((p) => p.id);
      const updated = await updateKnownFace(
        face.id,
        {
          name: trimmedName,
          company: trimmedCompany,
          branch: trimmedBranch,
          role: trimmedRole,
        },
        newFiles,
        keptIds
      );
      onSaved(updated);
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to update member");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="relative max-w-2xl w-full bg-gray-900 border border-gray-700 rounded-xl p-5 shadow-2xl space-y-4 max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-gray-800 pb-3">
          <div>
            <h2 className="text-base sm:text-lg font-bold text-white">Edit Known Member</h2>
            <p className="text-xs text-gray-400">Update profile details and reference photos for {face.name}</p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white text-base px-2 py-1 rounded bg-gray-800"
          >
            ✕
          </button>
        </div>

        <form onSubmit={handleSave} className="space-y-4">
          <div>
            <label className="text-xs text-gray-300 font-medium block mb-1">
              Full Name <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onBlur={() => setTouched((prev) => ({ ...prev, name: true }))}
              placeholder="Full name"
              className={`w-full bg-gray-800 rounded px-3 py-2 text-sm text-white focus:outline-none placeholder-gray-500 ${
                (touched.name || submitAttempted) && !isNameValid
                  ? "border border-red-500"
                  : "border border-gray-700 focus:border-blue-500"
              }`}
            />
            {(touched.name || submitAttempted) && !isNameValid && (
              <p className="text-xs text-red-400 mt-1">Full name is required</p>
            )}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <label className="text-xs text-gray-300 font-medium block mb-1">
                Company / Organization <span className="text-red-400">*</span>
              </label>
              <input
                type="text"
                value={company}
                onChange={(e) => setCompany(e.target.value)}
                onBlur={() => setTouched((prev) => ({ ...prev, company: true }))}
                placeholder="Company / Organization"
                className={`w-full bg-gray-800 rounded px-3 py-2 text-sm text-white focus:outline-none placeholder-gray-500 ${
                  (touched.company || submitAttempted) && !isCompanyValid
                    ? "border border-red-500"
                    : "border border-gray-700 focus:border-blue-500"
                }`}
              />
              {(touched.company || submitAttempted) && !isCompanyValid && (
                <p className="text-xs text-red-400 mt-1">Company / Organization is required</p>
              )}
            </div>

            <div>
              <label className="text-xs text-gray-300 font-medium block mb-1">
                Branch / Location <span className="text-red-400">*</span>
              </label>
              <input
                type="text"
                value={branch}
                onChange={(e) => setBranch(e.target.value)}
                onBlur={() => setTouched((prev) => ({ ...prev, branch: true }))}
                placeholder="Branch / Location"
                className={`w-full bg-gray-800 rounded px-3 py-2 text-sm text-white focus:outline-none placeholder-gray-500 ${
                  (touched.branch || submitAttempted) && !isBranchValid
                    ? "border border-red-500"
                    : "border border-gray-700 focus:border-blue-500"
                }`}
              />
              {(touched.branch || submitAttempted) && !isBranchValid && (
                <p className="text-xs text-red-400 mt-1">Branch / Location is required</p>
              )}
            </div>

            <div>
              <label className="text-xs text-gray-300 font-medium block mb-1">
                Role / Designation <span className="text-red-400">*</span>
              </label>
              <input
                type="text"
                value={role}
                onChange={(e) => setRole(e.target.value)}
                onBlur={() => setTouched((prev) => ({ ...prev, role: true }))}
                placeholder="Role / Designation"
                className={`w-full bg-gray-800 rounded px-3 py-2 text-sm text-white focus:outline-none placeholder-gray-500 ${
                  (touched.role || submitAttempted) && !isRoleValid
                    ? "border border-red-500"
                    : "border border-gray-700 focus:border-blue-500"
                }`}
              />
              {(touched.role || submitAttempted) && !isRoleValid && (
                <p className="text-xs text-red-400 mt-1">Role / Designation is required</p>
              )}
            </div>
          </div>

          {/* Photos Management */}
          <div className="space-y-2 border-t border-gray-800 pt-3">
            <div className="flex items-center justify-between">
              <label className="text-xs text-gray-300 font-medium">
                Reference Photos ({totalPhotos}/4) <span className="text-red-400">*</span>
              </label>
              <span className="text-xs text-gray-400">1 to 4 photos (at least 1 required)</span>
            </div>

            {loadingPhotos ? (
              <p className="text-xs text-gray-500">Loading photos...</p>
            ) : (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
                {keptExistingPhotos.map((p, idx) => {
                  const isLocked = p.revert_locked;
                  return (
                    <div key={p.id} className="relative group rounded-lg overflow-hidden border border-gray-700 bg-gray-950 aspect-square">
                      <img
                        src={snapshotUrl(p.photo_path)}
                        alt={`Photo ${idx + 1}`}
                        className="w-full h-full object-cover"
                      />
                      {p.is_cover && (
                        <span className="absolute top-1 left-1 text-[10px] bg-blue-600 text-white rounded px-1.5 py-0.5 font-medium shadow">
                          Cover
                        </span>
                      )}
                      {isLocked && (
                        <span className="absolute top-1 right-1 text-[9px] bg-red-700 text-white rounded px-1 py-0.5 font-bold shadow">
                          🔒 Locked
                        </span>
                      )}
                      <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition flex items-center justify-center p-2">
                        <button
                          type="button"
                          onClick={() => handleRemoveExistingPhoto(p.id)}
                          disabled={totalPhotos <= 1 || isLocked}
                          className={`text-xs rounded px-2.5 py-1 font-medium transition ${
                            isLocked || totalPhotos <= 1
                              ? "bg-gray-800 text-gray-500 cursor-not-allowed border border-gray-700 opacity-60"
                              : "bg-red-600 hover:bg-red-500 text-white"
                          }`}
                          title={
                            isLocked
                              ? "🔒 Locked by 48h revert lock"
                              : totalPhotos <= 1
                              ? "At least 1 photo required"
                              : "Remove photo"
                          }
                        >
                          Remove
                        </button>
                      </div>
                    </div>
                  );
                })}

                {newFiles.map((file, idx) => (
                  <div key={idx} className="relative group rounded-lg overflow-hidden border border-blue-500/50 bg-gray-950 aspect-square">
                    <img
                      src={newPreviews[idx] || ""}
                      alt={`New photo ${idx + 1}`}
                      className="w-full h-full object-cover"
                    />
                    <span className="absolute top-1 left-1 text-[10px] bg-emerald-600 text-white rounded px-1.5 py-0.5 font-medium shadow">
                      New
                    </span>
                    <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition flex items-center justify-center p-2">
                      <button
                        type="button"
                        onClick={() => handleRemoveNewFile(idx)}
                        disabled={totalPhotos <= 1}
                        className={`text-xs rounded px-2.5 py-1 font-medium transition ${
                          totalPhotos <= 1
                            ? "bg-gray-800 text-gray-500 cursor-not-allowed border border-gray-700 opacity-60"
                            : "bg-red-600 hover:bg-red-500 text-white"
                        }`}
                        title={totalPhotos <= 1 ? "At least 1 photo required" : "Remove photo"}
                      >
                        Remove
                      </button>
                    </div>
                  </div>
                ))}

                {totalPhotos < 4 && (
                  <label className="rounded-lg border-2 border-dashed border-gray-700 hover:border-gray-500 aspect-square flex flex-col items-center justify-center cursor-pointer text-gray-400 hover:text-white transition bg-gray-800/40">
                    <span className="text-xl leading-none mb-1">+</span>
                    <span className="text-xs">Add Photo</span>
                    <input
                      type="file"
                      accept=".jpg,.jpeg,image/jpeg"
                      multiple
                      className="hidden"
                      onChange={handleAddNewFiles}
                    />
                  </label>
                )}
              </div>
            )}

            {!isPhotosCountValid && (
              <p className="text-xs text-red-400 mt-1">
                {totalPhotos < 1
                  ? "Please keep or upload at least 1 photo"
                  : `Maximum 4 photos allowed (currently ${totalPhotos})`}
              </p>
            )}
          </div>

          {error && <p className="text-xs text-red-400">{error}</p>}

          <div className="flex items-center justify-end gap-2 pt-3 border-t border-gray-800">
            <button
              type="button"
              onClick={onClose}
              disabled={saving}
              className="bg-gray-800 hover:bg-gray-700 text-gray-300 rounded px-4 py-2 text-sm font-medium transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!isFormValid || saving}
              className={`rounded px-4 py-2 text-sm font-medium transition ${
                !isFormValid || saving
                  ? "bg-gray-800 text-gray-500 cursor-not-allowed border border-gray-700"
                  : "bg-blue-600 hover:bg-blue-500 text-white"
              }`}
            >
              {saving ? "Saving Changes..." : "Save Changes"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function RegisterFace({ onRegistered, knownFaces = [] }) {
  const [name, setName] = useState("");
  const [company, setCompany] = useState("");
  const [branch, setBranch] = useState("");
  const [role, setRole] = useState("");
  const [files, setFiles] = useState([]);
  const [status, setStatus] = useState("");
  const [expandedId, setExpandedId] = useState(null);
  const [editingPerson, setEditingPerson] = useState(null);
  const [touched, setTouched] = useState({ name: false, company: false, branch: false, role: false, photos: false });
  const [submitAttempted, setSubmitAttempted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [showDropdown, setShowDropdown] = useState(false);

  const trimmedName = name.trim();
  const trimmedCompany = company.trim();
  const trimmedBranch = branch.trim();
  const trimmedRole = role.trim();

  const isNameValid = trimmedName.length > 0;
  const isCompanyValid = trimmedCompany.length > 0;
  const isBranchValid = trimmedBranch.length > 0;
  const isRoleValid = trimmedRole.length > 0;

  // Real-time duplicate name check
  const duplicatePerson = knownFaces.find(
    (f) => f.name.trim().toLowerCase() === trimmedName.toLowerCase()
  );
  const isDuplicateName = Boolean(trimmedName) && Boolean(duplicatePerson);

  // Dynamic dropdown suggestions as user types
  const matchingSuggestions = trimmedName.length > 0
    ? knownFaces.filter((f) =>
        f.name.toLowerCase().includes(trimmedName.toLowerCase())
      )
    : [];

  const isFormValid =
    isNameValid && isCompanyValid && isBranchValid && isRoleValid && !isDuplicateName;

  const handleFileChange = (e) => {
    setTouched((prev) => ({ ...prev, photos: true }));
    const selected = Array.from(e.target.files);
    const nonJpg = selected.filter(
      (f) => !/\.(jpe?g)$/i.test(f.name) && f.type !== "image/jpeg"
    );
    if (nonJpg.length > 0) {
      setStatus(
        `❌ Only JPG/JPEG photos are supported. Rejected: ${nonJpg.map((f) => f.name).join(", ")}`
      );
      const jpgOnly = selected.filter((f) => !nonJpg.includes(f));
      setFiles(jpgOnly);
      return;
    }
    setStatus("");
    setFiles(selected);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitAttempted(true);
    if (!isFormValid) return;

    setBusy(true);
    setStatus("Registering...");
    try {
      const result = await registerFace(trimmedName, files, {
        company: trimmedCompany,
        branch: trimmedBranch,
        role: trimmedRole,
      });
      setStatus(`✅ Registered ${result.name}`);
      setName("");
      setCompany("");
      setBranch("");
      setRole("");
      setFiles([]);
      setShowDropdown(false);
      setTouched({ name: false, company: false, branch: false, role: false, photos: false });
      setSubmitAttempted(false);
      onRegistered?.();
    } catch (err) {
      setStatus(`❌ ${err.response?.data?.detail || "Registration failed"}`);
    } finally {
      setBusy(false);
    }
  };

  const handleRemoveToUnknown = async (id, personName) => {
    if (
      !confirm(
        `Move ${personName} back to Unknown? Their history and photos stay — they'll just move out of Known People.`
      )
    )
      return;
    try {
      await revertFaceToUnknown(id);
    } catch (err) {
      alert(err.response?.data?.detail || "Failed to move back to Unknown");
      return;
    }
    if (expandedId === id) setExpandedId(null);
    onRegistered?.();
  };

  return (
    <div className="rounded-xl border border-gray-700 bg-gray-900 p-4">
      <h2 className="font-semibold mb-1">Register a Known Member</h2>
      <p className="text-xs text-gray-500 mb-3">
        All profile fields (Name, Company, Branch, Role) are required. Names must be unique. Reference photos are optional.
      </p>
      <form onSubmit={handleSubmit} className="flex flex-col gap-2 mb-4">
        {/* Full Name input with Real-Time Duplicate Validation & Dynamic Dropdown */}
        <div className="relative">
          <input
            className={`w-full bg-gray-800 rounded px-3 py-2 text-sm text-white focus:outline-none placeholder-gray-500 transition ${
              isDuplicateName
                ? "border-2 border-amber-500 bg-amber-950/20 text-amber-100 focus:border-amber-400"
                : (touched.name || submitAttempted) && !isNameValid
                ? "border border-red-500"
                : "border border-gray-700 focus:border-blue-500"
            }`}
            placeholder="Full name *"
            value={name}
            onChange={(e) => {
              setName(e.target.value);
              setShowDropdown(true);
            }}
            onFocus={() => setShowDropdown(true)}
            onBlur={() => {
              setTouched((p) => ({ ...p, name: true }));
              setTimeout(() => setShowDropdown(false), 200);
            }}
          />

          {/* Dynamic Dropdown showing matching existing names */}
          {showDropdown && matchingSuggestions.length > 0 && (
            <div className="absolute left-0 right-0 top-full mt-1 bg-gray-900 border border-gray-700 rounded-lg shadow-2xl z-30 max-h-52 overflow-y-auto divide-y divide-gray-800">
              <div className="px-3 py-1.5 text-[11px] font-semibold text-gray-400 uppercase tracking-wider bg-gray-950 flex items-center justify-between">
                <span>Existing Registered Members</span>
                <span className="text-[10px] text-gray-500">{matchingSuggestions.length} match(es)</span>
              </div>
              {matchingSuggestions.map((m) => {
                const isExact = m.name.trim().toLowerCase() === trimmedName.toLowerCase();
                return (
                  <div
                    key={m.id}
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => {
                      setName(m.name);
                      setShowDropdown(false);
                    }}
                    className={`px-3 py-2 text-xs flex items-center justify-between cursor-pointer transition ${
                      isExact
                        ? "bg-amber-950/60 text-amber-200 hover:bg-amber-950/80"
                        : "text-gray-300 hover:bg-gray-800 hover:text-white"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span className="font-semibold">{m.name}</span>
                      {(m.company || m.role) && (
                        <span className="text-gray-400 text-[11px]">
                          • {[m.company, m.role].filter(Boolean).join(" • ")}
                        </span>
                      )}
                    </div>
                    {isExact ? (
                      <span className="text-[10px] bg-amber-900/90 border border-amber-600 text-amber-200 px-2 py-0.5 rounded font-bold">
                        ⚠️ Name Already Exists
                      </span>
                    ) : (
                      <span className="text-[10px] bg-gray-800 text-gray-400 px-1.5 py-0.5 rounded">
                        Registered
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {/* Clear real-time warning message when name already exists */}
          {isDuplicateName && (
            <div className="flex items-start gap-2 p-2.5 rounded-lg bg-amber-950/70 border border-amber-500/80 text-amber-200 text-xs mt-1.5 shadow-md">
              <span className="text-base leading-none select-none text-amber-400">⚠️</span>
              <div className="space-y-0.5">
                <p className="font-semibold text-amber-300">
                  A person named "{duplicatePerson.name}" already exists in the system.
                </p>
                <p className="text-[11px] text-amber-400/90">
                  Duplicate names are not allowed
                  {duplicatePerson.company ? ` (${[duplicatePerson.company, duplicatePerson.branch, duplicatePerson.role].filter(Boolean).join(" • ")})` : ""}.
                  Please enter a unique name.
                </p>
              </div>
            </div>
          )}

          {(touched.name || submitAttempted) && !isNameValid && !isDuplicateName && (
            <p className="text-xs text-red-400 mt-1">Full name is required</p>
          )}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          <div>
            <input
              className={`w-full bg-gray-800 rounded px-3 py-2 text-sm text-white focus:outline-none placeholder-gray-500 ${
                (touched.company || submitAttempted) && !isCompanyValid
                  ? "border border-red-500"
                  : "border border-gray-700 focus:border-blue-500"
              }`}
              placeholder="Company / Organization *"
              value={company}
              onChange={(e) => setCompany(e.target.value)}
              onBlur={() => setTouched((p) => ({ ...p, company: true }))}
            />
            {(touched.company || submitAttempted) && !isCompanyValid && (
              <p className="text-xs text-red-400 mt-1">Company / Organization is required</p>
            )}
          </div>

          <div>
            <input
              className={`w-full bg-gray-800 rounded px-3 py-2 text-sm text-white focus:outline-none placeholder-gray-500 ${
                (touched.branch || submitAttempted) && !isBranchValid
                  ? "border border-red-500"
                  : "border border-gray-700 focus:border-blue-500"
              }`}
              placeholder="Branch / Location *"
              value={branch}
              onChange={(e) => setBranch(e.target.value)}
              onBlur={() => setTouched((p) => ({ ...p, branch: true }))}
            />
            {(touched.branch || submitAttempted) && !isBranchValid && (
              <p className="text-xs text-red-400 mt-1">Branch / Location is required</p>
            )}
          </div>

          <div>
            <input
              className={`w-full bg-gray-800 rounded px-3 py-2 text-sm text-white focus:outline-none placeholder-gray-500 ${
                (touched.role || submitAttempted) && !isRoleValid
                  ? "border border-red-500"
                  : "border border-gray-700 focus:border-blue-500"
              }`}
              placeholder="Role / Designation *"
              value={role}
              onChange={(e) => setRole(e.target.value)}
              onBlur={() => setTouched((p) => ({ ...p, role: true }))}
            />
            {(touched.role || submitAttempted) && !isRoleValid && (
              <p className="text-xs text-red-400 mt-1">Role / Designation is required</p>
            )}
          </div>
        </div>

        <div>
          <label className="text-xs text-gray-400 mb-1 block">
            Reference Photos (Optional, up to 4 JPG/JPEG photos)
          </label>
          <input
            type="file"
            accept=".jpg,.jpeg,image/jpeg"
            multiple
            className="text-sm text-gray-300 file:mr-3 file:py-1.5 file:px-3 file:rounded file:border-0 file:text-xs file:font-medium file:bg-gray-800 file:text-gray-200 hover:file:bg-gray-700 cursor-pointer"
            onChange={handleFileChange}
          />
          {files.length > 0 && (
            <p className="text-xs text-gray-400 mt-1">{files.length} JPG photo(s) selected</p>
          )}
          {files.length > 4 && (
            <p className="text-xs text-red-400 mt-1">Maximum 4 photos allowed (currently {files.length} selected)</p>
          )}
        </div>

        <button
          type="submit"
          disabled={!isFormValid || isDuplicateName || busy}
          className={`rounded px-4 py-2 text-sm font-medium transition ${
            !isFormValid || isDuplicateName || busy
              ? "bg-gray-800 text-gray-500 cursor-not-allowed border border-gray-700"
              : "bg-blue-600 hover:bg-blue-500 text-white"
          }`}
        >
          {busy ? "Registering..." : "Register Member"}
        </button>
        {status && <p className="text-xs text-gray-400">{status}</p>}
      </form>

      {knownFaces.length > 0 && (
        <div className="space-y-2 border-t border-gray-800 pt-3">
          <p className="text-xs text-gray-400 mb-1">Registered members (click a name to view profile)</p>
          {knownFaces.map((f) => {
            const isLocked = f.revert_locked;
            const hoursLeftStr = formatHoursLeft(f.revert_hours_left);

            return (
              <div key={f.id}>
                <div className="flex items-center justify-between bg-gray-800 rounded px-3 py-2">
                  <div
                    className="flex items-center gap-2 cursor-pointer flex-1"
                    onClick={() => setExpandedId(expandedId === f.id ? null : f.id)}
                  >
                    {f.photo_path && (
                      <img
                        src={snapshotUrl(f.photo_path)}
                        alt={f.name}
                        className="w-8 h-8 object-cover rounded-full"
                      />
                    )}
                    <div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-medium">{f.name}</span>
                        <span className="text-xs text-gray-500">({f.photo_count} photos)</span>
                        {isLocked && (
                          <span className="text-[10px] bg-red-900/80 border border-red-600 text-red-200 px-1.5 py-0.5 rounded font-bold">
                            🔒 Locked
                          </span>
                        )}
                        {!isLocked && f.revert_hours_left !== null && f.revert_hours_left !== undefined && (
                          <span
                            className={`text-[10px] px-1.5 py-0.5 rounded font-semibold ${
                              f.revert_hours_left <= 12
                                ? "bg-yellow-900/80 border border-yellow-600 text-yellow-200"
                                : "bg-emerald-900/80 border border-emerald-600 text-emerald-200"
                            }`}
                          >
                            Revert allowed: {hoursLeftStr}
                          </span>
                        )}
                      </div>
                      {(f.company || f.branch || f.role) && (
                        <div className="text-xs text-gray-400">
                          {[f.company, f.branch, f.role].filter(Boolean).join(" • ")}
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setEditingPerson(f);
                      }}
                      className="text-xs rounded px-3 py-1 font-medium bg-blue-600/80 hover:bg-blue-600 text-white transition"
                      title="Edit profile details and photos"
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        if (isLocked) return;
                        handleRemoveToUnknown(f.id, f.name);
                      }}
                      disabled={isLocked}
                      className={`text-xs rounded px-3 py-1 font-medium transition ${
                        isLocked
                          ? "bg-gray-900 text-gray-600 border border-gray-700 cursor-not-allowed opacity-50"
                          : "bg-yellow-600 hover:bg-yellow-500 text-white"
                      }`}
                      title={
                        isLocked
                          ? "Revert window (48 hours) closed. Changes are not allowed anymore."
                          : "Move back to Unknown — history and photos are kept"
                      }
                    >
                      {isLocked ? "🔒 Locked" : "Remove"}
                    </button>
                  </div>
                </div>
                {expandedId === f.id && (
                  <PersonProfile
                    face={f}
                    onClose={() => setExpandedId(null)}
                    onChanged={onRegistered}
                  />
                )}
              </div>
            );
          })}
        </div>
      )}

      {editingPerson && (
        <EditPersonModal
          face={editingPerson}
          onClose={() => setEditingPerson(null)}
          onSaved={(updated) => {
            setEditingPerson(null);
            setStatus(`✅ Profile updated for ${updated.name}`);
            onRegistered?.();
          }}
        />
      )}
    </div>
  );
}
