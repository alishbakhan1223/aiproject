import { snapshotUrl } from "../api";

export default function RecentScenesView({ scenes = [], onSelectFace, loading = false }) {
  const getConfidenceColor = (pct) => {
    if (pct == null) return "text-gray-400 bg-gray-800 border-gray-700";
    if (pct >= 75) return "text-emerald-300 bg-emerald-950/80 border-emerald-700/80";
    if (pct >= 50) return "text-amber-300 bg-amber-950/80 border-amber-700/80";
    return "text-rose-300 bg-rose-950/80 border-rose-700/80";
  };

  if (loading && scenes.length === 0) {
    return (
      <div className="p-12 text-center text-gray-400 bg-gray-900/60 rounded-xl border border-gray-800 animate-pulse">
        <span className="text-2xl block mb-2">🔄</span>
        <span>Loading recent multi-person scenes...</span>
      </div>
    );
  }

  if (scenes.length === 0) {
    return (
      <div className="p-12 text-center text-gray-500 bg-gray-900/60 rounded-xl border border-gray-800">
        <span className="text-3xl block mb-2">👥</span>
        <h4 className="text-sm font-semibold text-gray-300">No multi-person scenes recorded yet</h4>
        <p className="text-xs text-gray-500 mt-1">
          When cameras detect people, annotated full-scene snapshots and individual face crops will appear here.
        </p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
      {scenes.map((scene, idx) => {
        const faceCount = scene.faces?.length || scene.face_count || 1;
        const sceneImg = scene.scene_image_url || scene.scene_snapshot_path || (scene.faces?.[0]?.face_crop_path);

        return (
          <div
            key={scene.scene_id || idx}
            className="bg-gray-900/90 border border-gray-800 rounded-2xl overflow-hidden shadow-xl hover:border-gray-700 transition flex flex-col justify-between"
          >
            {/* Card Header */}
            <div className="px-5 py-3.5 bg-gray-950/80 border-b border-gray-800 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-sm font-bold text-white flex items-center gap-1.5">
                  <span>📷</span>
                  <span>{scene.camera_name || "Camera 1"}</span>
                </span>
                <span className="text-xs text-gray-500">•</span>
                <span className="text-xs text-gray-400 font-mono">
                  {scene.timestamp ? new Date(scene.timestamp).toLocaleString() : "Recent"}
                </span>
              </div>

              <div className="flex items-center gap-2">
                <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-950/80 text-blue-300 border border-blue-800/80">
                  <span>👥</span>
                  <span>{faceCount} {faceCount === 1 ? "Person" : "Persons"}</span>
                </span>
              </div>
            </div>

            {/* Main Annotated Scene Snapshot */}
            <div className="relative bg-black w-full min-h-[220px] max-h-[340px] flex items-center justify-center overflow-hidden group">
              {sceneImg ? (
                <img
                  src={snapshotUrl(sceneImg)}
                  alt={`Scene at ${scene.camera_name}`}
                  className="w-full h-full max-h-[340px] object-contain cursor-pointer group-hover:scale-[1.01] transition duration-300"
                  onClick={() => {
                    if (scene.faces?.[0] && onSelectFace) {
                      onSelectFace(scene.faces[0], scene);
                    }
                  }}
                  onError={(e) => {
                    e.target.onerror = null;
                    if (scene.faces?.[0]?.face_crop_path) {
                      e.target.src = snapshotUrl(scene.faces[0].face_crop_path);
                    }
                  }}
                />
              ) : (
                <div className="text-gray-500 text-xs py-16 flex flex-col items-center gap-1">
                  <span>📷</span>
                  <span>Scene snapshot unavailable</span>
                </div>
              )}

              <div className="absolute top-2 left-2 bg-black/60 backdrop-blur-sm px-2 py-1 rounded text-[10px] font-mono text-gray-300 border border-white/10 pointer-events-none">
                FULL SCENE SNAPSHOT
              </div>
            </div>

            {/* Individual Face Crops Strip */}
            <div className="p-4 bg-gray-950/90 border-t border-gray-800 space-y-2">
              <div className="flex items-center justify-between text-xs text-gray-400">
                <span className="font-semibold uppercase tracking-wider text-[10px]">
                  Detected Face Crops ({faceCount}):
                </span>
                <span className="text-[11px] text-gray-500">Click any crop for face detail view</span>
              </div>

              <div className="flex gap-3 overflow-x-auto pb-1 pt-1">
                {(scene.faces || []).map((face, fIdx) => {
                  const confPct = face.confidence_percent ?? Math.round((face.confidence || 0.85) * 100);
                  const isUnknown = face.is_unknown !== false;
                  const cropUrl = face.face_image_url || face.face_crop_path;

                  return (
                    <div
                      key={face.event_id || fIdx}
                      onClick={() => onSelectFace && onSelectFace(face, scene)}
                      className="bg-gray-900 border border-gray-800 hover:border-blue-500/80 rounded-xl p-2 flex items-center gap-3 shrink-0 cursor-pointer shadow-md hover:bg-gray-850 transition duration-200 group"
                    >
                      {/* Face Thumbnail */}
                      <div className="w-12 h-14 rounded-lg bg-black border border-gray-700 overflow-hidden shrink-0 flex items-center justify-center">
                        {cropUrl ? (
                          <img
                            src={snapshotUrl(cropUrl)}
                            alt={face.person_name}
                            className="w-full h-full object-cover group-hover:scale-105 transition"
                          />
                        ) : (
                          <span className="text-base text-gray-500">👤</span>
                        )}
                      </div>

                      {/* Face Info */}
                      <div className="flex flex-col text-left pr-1">
                        <div className="flex items-center gap-1.5">
                          <span className="text-xs font-bold text-white max-w-[110px] truncate">
                            {face.person_name || (isUnknown ? "Unknown" : "Known")}
                          </span>
                          <span
                            className={`px-1.5 py-0.2 rounded text-[9px] font-extrabold uppercase tracking-wide border ${
                              isUnknown
                                ? "bg-rose-950 text-rose-300 border-rose-800"
                                : "bg-green-950 text-green-300 border-green-800"
                            }`}
                          >
                            {isUnknown ? "Unknown" : "Known"}
                          </span>
                        </div>

                        <div className="flex items-center gap-2 mt-1">
                          <span
                            className={`px-1.5 py-0.5 rounded text-[10px] font-bold border ${getConfidenceColor(
                              confPct
                            )}`}
                          >
                            {confPct}%
                          </span>
                          <span className="text-[10px] text-gray-400 capitalize">
                            {face.zone || "inside"}
                          </span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
