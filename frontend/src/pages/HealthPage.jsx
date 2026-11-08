import { useEffect, useState, useCallback } from "react";
import { getHealth } from "../api";

// ── Status dots ─────────────────────────────────────────────────────────────
function StatusDot({ ok }) {
  return (
    <span
      className={`w-2 h-2 rounded-full inline-block ${ok ? "bg-green-500" : "bg-red-500"}`}
    />
  );
}

// ── Performance colour based on thresholds ───────────────────────────────────
// returns: "green" | "yellow" | "red" | "gray"
function perfColor(value, greenMax, yellowMax) {
  if (value == null) return "gray";
  if (value <= greenMax) return "green";
  if (value <= yellowMax) return "yellow";
  return "red";
}

function PerfBadge({ value, unit = "", greenMax, yellowMax, decimals = 0 }) {
  if (value == null) return <span className="text-gray-600">—</span>;
  const color = perfColor(value, greenMax, yellowMax);
  const cls = {
    green: "text-green-400",
    yellow: "text-yellow-400",
    red: "text-red-400",
    gray: "text-gray-500",
  }[color];
  return (
    <span className={cls}>
      {Number(value).toFixed(decimals)}
      {unit}
    </span>
  );
}

// ── FPS badge (higher = better, so thresholds reversed) ──────────────────────
function FpsBadge({ value }) {
  if (value == null) return <span className="text-gray-600">—</span>;
  const color = value >= 20 ? "green" : value >= 10 ? "yellow" : "red";
  const cls = { green: "text-green-400", yellow: "text-yellow-400", red: "text-red-400" }[color];
  return <span className={cls}>{Number(value).toFixed(1)}</span>;
}

// ── Resource bar ─────────────────────────────────────────────────────────────
function ResourceBar({ label, value }) {
  if (value == null) return null;
  const color = value < 70 ? "bg-green-500" : value < 90 ? "bg-yellow-400" : "bg-red-500";
  return (
    <div className="flex items-center gap-3 text-sm">
      <span className="w-16 text-gray-400 text-xs">{label}</span>
      <div className="flex-1 bg-gray-800 rounded-full h-2">
        <div className={`${color} h-2 rounded-full transition-all`} style={{ width: `${value}%` }} />
      </div>
      <span className="w-12 text-right text-gray-300">{value.toFixed(1)}%</span>
    </div>
  );
}

// ── Expanded camera detail panel ──────────────────────────────────────────────
function CameraDetail({ w }) {
  return (
    <tr className="border-t border-gray-700 bg-gray-950">
      <td colSpan={9} className="px-6 py-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs text-gray-400">
          <div>
            <p className="text-gray-500 mb-1">JPEG encode</p>
            <PerfBadge value={w.jpeg_encode_ms} unit="ms" greenMax={10} yellowMax={25} decimals={1} />
          </div>
          <div>
            <p className="text-gray-500 mb-1">YOLO inference</p>
            <PerfBadge value={w.yolo_inference_ms} unit="ms" greenMax={150} yellowMax={400} decimals={0} />
          </div>
          <div>
            <p className="text-gray-500 mb-1">InsightFace inference</p>
            <PerfBadge value={w.insightface_inference_ms} unit="ms" greenMax={150} yellowMax={400} decimals={0} />
          </div>
          <div>
            <p className="text-gray-500 mb-1">Frames delivered</p>
            <span className="text-gray-300">{w.frames_delivered ?? "—"}</span>
          </div>
          <div>
            <p className="text-gray-500 mb-1">Stream errors</p>
            <span className={w.stream_errors > 0 ? "text-red-400" : "text-gray-300"}>
              {w.stream_errors ?? 0}
            </span>
          </div>
          <div>
            <p className="text-gray-500 mb-1">Source FPS</p>
            <span className="text-gray-300">{w.fps_source ?? "—"}</span>
          </div>
          <div>
            <p className="text-gray-500 mb-1">Last detection</p>
            <span className="text-gray-300">
              {w.latest_detection_at ? new Date(w.latest_detection_at).toLocaleTimeString() : "—"}
            </span>
          </div>
          <div>
            <p className="text-gray-500 mb-1">State</p>
            <span className={
              w.state === "connected" ? "text-green-400"
              : w.state === "reconnecting" ? "text-yellow-400"
              : "text-gray-400"
            }>{w.state ?? "—"}</span>
          </div>
        </div>
      </td>
    </tr>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function HealthPage() {
  const [health, setHealth] = useState(null);
  const [error, setError] = useState(false);
  const [expanded, setExpanded] = useState({});

  const refresh = useCallback(async () => {
    try {
      setHealth(await getHealth());
      setError(false);
    } catch {
      setError(true);
    }
  }, []);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 5000);
    return () => clearInterval(interval);
  }, [refresh]);

  const toggleExpand = (id) =>
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));

  return (
    <div className="p-6 space-y-6">
      <header>
        <h1 className="text-xl font-bold">System Health</h1>
        <p className="text-sm text-gray-400">
          Backend, database, queue, per-camera performance, and system resources
        </p>
      </header>

      {error && (
        <p className="text-red-400 text-sm">Could not reach the backend API.</p>
      )}

      {health && (
        <>
          {/* ── Service cards ── */}
          <div className="grid grid-cols-3 gap-4 max-w-xl">
            {[
              { label: "API", ok: health.api_status === "running", text: health.api_status },
              {
                label: "Database",
                ok: health.database_connected,
                text: health.database_connected ? "Connected" : "Down",
              },
              {
                label: "Redis",
                ok: health.redis_connected,
                text: health.redis_connected ? "Connected" : "Down",
              },
            ].map(({ label, ok, text }) => (
              <div key={label} className="bg-gray-900 border border-gray-700 rounded-xl p-4">
                <p className="text-xs text-gray-400 mb-1">{label}</p>
                <div className="flex items-center gap-2">
                  <StatusDot ok={ok} />
                  <span className="text-sm">{text}</span>
                </div>
              </div>
            ))}
          </div>

          {/* ── System resources ── */}
          {health.system && (
            <div className="bg-gray-900 border border-gray-700 rounded-xl p-4 max-w-xl space-y-2">
              <p className="text-sm font-semibold text-gray-300 mb-3">System Resources</p>
              <ResourceBar label="CPU" value={health.system.cpu_percent} />
              <ResourceBar label="RAM" value={health.system.ram_percent} />
              {health.system.gpu_percent != null && (
                <ResourceBar label="GPU" value={health.system.gpu_percent} />
              )}
              {health.system.gpu_memory_percent != null && (
                <ResourceBar label="GPU Mem" value={health.system.gpu_memory_percent} />
              )}
            </div>
          )}

          {/* ── Camera table ── */}
          <div>
            <h2 className="font-semibold mb-3">Camera Workers</h2>
            <p className="text-xs text-gray-500 mb-2">
              Click a row to expand detailed metrics. Colours: 
              <span className="text-green-400 ml-1">good</span> ·
              <span className="text-yellow-400 ml-1">warning</span> ·
              <span className="text-red-400 ml-1">critical</span>
            </p>
            <div className="rounded-xl border border-gray-700 bg-gray-900 overflow-x-auto">
              <table className="w-full text-sm min-w-max">
                <thead className="bg-gray-800 text-gray-400">
                  <tr>
                    <th className="text-left p-3">Camera</th>
                    <th className="text-left p-3">Status</th>
                    <th className="text-left p-3 whitespace-nowrap">Cap FPS</th>
                    <th className="text-left p-3 whitespace-nowrap">Frame Age</th>
                    <th className="text-left p-3 whitespace-nowrap">YOLO FPS</th>
                    <th className="text-left p-3 whitespace-nowrap">Detect Age</th>
                    <th className="text-left p-3 whitespace-nowrap">Dropped</th>
                    <th className="text-left p-3 whitespace-nowrap">Reconnects</th>
                    <th className="text-left p-3 whitespace-nowrap">Last Frame</th>
                  </tr>
                </thead>
                <tbody>
                  {health.workers.map((w) => (
                    <>
                      <tr
                        key={w.camera_id}
                        className="border-t border-gray-800 hover:bg-gray-800 cursor-pointer"
                        onClick={() => toggleExpand(w.camera_id)}
                      >
                        <td className="p-3 font-medium">
                          <span className="mr-1 text-gray-500 text-xs">
                            {expanded[w.camera_id] ? "▾" : "▸"}
                          </span>
                          {w.camera_name}
                        </td>
                        <td className="p-3">
                          <div className="flex items-center gap-2">
                            <StatusDot ok={w.running} />
                            {w.running ? "Running" : "Stopped"}
                          </div>
                        </td>
                        <td className="p-3">
                          <FpsBadge value={w.capture_fps} />
                        </td>
                        <td className="p-3">
                          <PerfBadge value={w.frame_age_ms} unit="ms" greenMax={100} yellowMax={300} decimals={0} />
                        </td>
                        <td className="p-3">
                          <FpsBadge value={w.yolo_fps} />
                        </td>
                        <td className="p-3">
                          <PerfBadge value={w.detection_frame_age_ms} unit="ms" greenMax={500} yellowMax={2000} decimals={0} />
                        </td>
                        <td className="p-3 text-gray-400">
                          {w.dropped_frames ?? 0} / {w.detection_frames_skipped ?? 0}
                        </td>
                        <td className="p-3">
                          <span className={w.reconnect_count > 3 ? "text-red-400" : w.reconnect_count > 0 ? "text-yellow-400" : "text-gray-400"}>
                            {w.reconnect_count ?? 0}
                          </span>
                        </td>
                        <td className="p-3 text-gray-400 text-xs">
                          {w.last_frame_at
                            ? new Date(w.last_frame_at).toLocaleTimeString()
                            : "—"}
                        </td>
                      </tr>
                      {expanded[w.camera_id] && <CameraDetail key={`${w.camera_id}-detail`} w={w} />}
                    </>
                  ))}
                  {health.workers.length === 0 && (
                    <tr>
                      <td colSpan={9} className="p-6 text-center text-gray-500">
                        No cameras have been started yet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            {/* Threshold legend */}
            <div className="mt-3 text-xs text-gray-600 space-y-0.5">
              <p>Frame age: <span className="text-green-400">{"< 100ms"}</span> · <span className="text-yellow-400">100–300ms</span> · <span className="text-red-400">{"> 300ms"}</span></p>
              <p>Detect age: <span className="text-green-400">{"< 500ms"}</span> · <span className="text-yellow-400">0.5–2s</span> · <span className="text-red-400">{"> 2s"}</span></p>
              <p>Capture/YOLO FPS: <span className="text-green-400">≥ 20</span> · <span className="text-yellow-400">10–20</span> · <span className="text-red-400">{"< 10"}</span></p>
              <p>Dropped = reader-thread drops (video) / Skipped = detection queue skips (AI, expected with real-time strategy)</p>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
