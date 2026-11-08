import { useEffect, useRef, useState } from "react";
import { getCameras, getZone, saveZone, deleteZone, videoFeedUrl, startCamera } from "../api";

export default function ZoneEditorPage() {
  const [cameras, setCameras] = useState([]);
  const [cameraId, setCameraId] = useState(null);
  const [points, setPoints] = useState([]); // in displayed-image pixel coords
  const [status, setStatus] = useState("");
  const imgRef = useRef(null);

  const fetchCameras = () => {
    getCameras().then((c) => {
      setCameras(c);
      if (c.length > 0 && !cameraId) setCameraId(c[0].id);
    });
  };

  useEffect(() => {
    fetchCameras();
  }, []);

  useEffect(() => {
    if (!cameraId) return;
    setPoints([]);
    setStatus("");
    getZone(cameraId).then((zone) => {
      if (zone && zone.points && zone.points.length > 0) {
        const convertPoints = () => {
          const img = imgRef.current;
          if (!img) return;
          const nw = img.naturalWidth || img.clientWidth || 640;
          const nh = img.naturalHeight || img.clientHeight || 480;
          const cw = img.clientWidth || nw;
          const ch = img.clientHeight || nh;
          const scaleX = cw / nw;
          const scaleY = ch / nh;
          setPoints(zone.points.map(([x, y]) => [x * scaleX, y * scaleY]));
        };

        const img = imgRef.current;
        if (img && img.complete && img.clientWidth > 0) {
          convertPoints();
        } else if (img) {
          img.onload = convertPoints;
        }
      }
    });
  }, [cameraId]);

  const handleImageClick = (e) => {
    if (!imgRef.current) return;
    const rect = imgRef.current.getBoundingClientRect();
    const x = Math.round(e.clientX - rect.left);
    const y = Math.round(e.clientY - rect.top);
    setPoints((p) => [...p, [x, y]]);
  };

  const handleSave = async () => {
    if (points.length < 3) {
      setStatus("⚠️ Add at least 3 points to form a zone polygon.");
      return;
    }
    const img = imgRef.current;
    if (!img) return;
    const nw = img.naturalWidth || img.clientWidth || 640;
    const nh = img.naturalHeight || img.clientHeight || 480;
    const cw = img.clientWidth || nw;
    const ch = img.clientHeight || nh;
    const scaleX = nw / cw;
    const scaleY = nh / ch;
    const naturalPoints = points.map(([x, y]) => [
      Math.round(x * scaleX),
      Math.round(y * scaleY),
    ]);
    try {
      await saveZone(cameraId, naturalPoints);
      setStatus("✅ Zone saved successfully! Running camera will enforce this zone.");
    } catch (err) {
      setStatus("❌ Failed to save zone: " + (err.response?.data?.detail || err.message));
    }
  };

  const handleClear = async () => {
    setPoints([]);
    try {
      await deleteZone(cameraId);
      setStatus("Zone cleared — full frame monitored again.");
    } catch (err) {
      setStatus("❌ Failed to clear zone.");
    }
  };

  const handleUndo = () => {
    setPoints((p) => p.slice(0, -1));
  };

  const handleStartCam = async () => {
    if (!cameraId) return;
    setStatus("Starting camera stream...");
    try {
      await startCamera(cameraId);
      fetchCameras();
      setStatus("Camera started!");
    } catch (err) {
      setStatus("Failed to start camera: " + (err.response?.data?.detail || err.message));
    }
  };

  const activeCamera = cameras.find((c) => c.id === cameraId);
  const polygonStr = points.map((p) => p.join(",")).join(" ");

  return (
    <div className="p-6 space-y-4">
      <header>
        <h1 className="text-xl font-bold">Zone Editor</h1>
        <p className="text-sm text-gray-400">
          Click on the live camera feed to draw a restricted zone polygon. Only detections inside this polygon will trigger alerts.
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-3">
        <select
          className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-white"
          value={cameraId || ""}
          onChange={(e) => setCameraId(Number(e.target.value))}
        >
          {cameras.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name} {c.is_active ? "🔴 (Live)" : "⚪ (Offline)"}
            </option>
          ))}
        </select>

        {activeCamera && !activeCamera.is_active && (
          <button
            onClick={handleStartCam}
            className="bg-green-600 hover:bg-green-500 text-white font-medium rounded px-4 py-2 text-sm transition"
          >
            Start Camera Stream
          </button>
        )}

        <button
          onClick={handleSave}
          disabled={points.length < 3}
          className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium rounded px-4 py-2 text-sm transition"
        >
          Save Zone
        </button>

        <button
          onClick={handleUndo}
          disabled={points.length === 0}
          className="bg-gray-700 hover:bg-gray-600 disabled:opacity-50 text-white rounded px-3 py-2 text-sm transition"
        >
          Undo Point
        </button>

        <button
          onClick={handleClear}
          className="bg-red-900/40 hover:bg-red-800/60 text-red-300 border border-red-700/50 rounded px-3 py-2 text-sm transition"
        >
          Clear Zone
        </button>

        {status && <span className="text-sm text-blue-400 font-medium">{status}</span>}
      </div>

      {!activeCamera && (
        <p className="text-sm text-gray-400">No cameras added yet. Please add a camera from Dashboard first.</p>
      )}

      {activeCamera && !activeCamera.is_active && (
        <div className="p-4 bg-yellow-900/20 border border-yellow-700/40 rounded text-yellow-300 text-sm">
          ⚠️ Camera <strong>{activeCamera.name}</strong> is currently offline. Click <strong>"Start Camera Stream"</strong> above to start live feed and draw your zone.
        </div>
      )}

      {activeCamera && activeCamera.is_active && (
        <div className="space-y-2">
          <p className="text-xs text-gray-400">
            Click points directly on the camera feed to draw a polygon. Click <strong>Save Zone</strong> when done (minimum 3 points).
          </p>

          <div className="relative inline-block border border-gray-700 rounded-lg overflow-hidden select-none bg-black">
            <img
              ref={imgRef}
              src={videoFeedUrl(cameraId)}
              alt="live feed"
              onClick={handleImageClick}
              className="block cursor-crosshair max-w-4xl min-w-[480px] h-auto"
            />
            <svg className="absolute inset-0 w-full h-full pointer-events-none">
              {points.length >= 3 && (
                <polygon points={polygonStr} fill="rgba(59, 130, 246, 0.3)" stroke="#3b82f6" strokeWidth="2.5" />
              )}
              {points.length === 2 && (
                <line x1={points[0][0]} y1={points[0][1]} x2={points[1][0]} y2={points[1][1]} stroke="#3b82f6" strokeWidth="2" />
              )}
              {points.map(([x, y], i) => (
                <g key={i}>
                  <circle cx={x} cy={y} r="5" fill="#3b82f6" stroke="#ffffff" strokeWidth="1.5" />
                  <text x={x + 7} y={y - 7} fill="#60a5fa" fontSize="12" fontWeight="bold">
                    {i + 1}
                  </text>
                </g>
              ))}
            </svg>
          </div>
        </div>
      )}
    </div>
  );
}

