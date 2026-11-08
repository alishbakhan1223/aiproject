import { useState } from "react";
import { addCamera, startCamera, stopCamera, videoFeedUrl } from "../api";

export default function LiveFeed({ cameras, refresh }) {
  const [name, setName] = useState("");
  const [source, setSource] = useState("0");
  const [viewingId, setViewingId] = useState(null);

  const handleAdd = async (e) => {
    e.preventDefault();
    if (!name) return;
    await addCamera(name, source);
    setName("");
    setSource("0");
    refresh();
  };

  return (
    <div className="rounded-xl border border-gray-700 bg-gray-900 p-4">
      <h2 className="font-semibold mb-3">Cameras</h2>

      <form onSubmit={handleAdd} className="flex gap-2 mb-4">
        <input
          className="bg-gray-800 rounded px-3 py-2 text-sm flex-1"
          placeholder="Camera name (e.g. Entrance)"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <input
          className="bg-gray-800 rounded px-3 py-2 text-sm w-40"
          placeholder="Source (0, rtsp://...)"
          value={source}
          onChange={(e) => setSource(e.target.value)}
        />
        <button className="bg-blue-600 hover:bg-blue-500 rounded px-4 py-2 text-sm">
          Add
        </button>
      </form>

      <div className="space-y-2">
        {cameras.map((c) => (
          <div key={c.id} className="bg-gray-800 rounded px-3 py-2">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium">{c.name}</p>
                <p className="text-xs text-gray-400">{c.source}</p>
              </div>
              <div className="flex items-center gap-2">
                <span
                  className={`w-2 h-2 rounded-full ${
                    c.is_active ? "bg-green-500" : "bg-gray-500"
                  }`}
                />
                {c.is_active ? (
                  <>
                    <button
                      onClick={() => setViewingId(viewingId === c.id ? null : c.id)}
                      className="text-xs bg-blue-600 hover:bg-blue-500 rounded px-3 py-1"
                    >
                      {viewingId === c.id ? "Hide" : "View"}
                    </button>
                    <button
                      onClick={async () => {
                        await stopCamera(c.id);
                        setViewingId(null);
                        refresh();
                      }}
                      className="text-xs bg-red-600 hover:bg-red-500 rounded px-3 py-1"
                    >
                      Stop
                    </button>
                  </>
                ) : (
                  <button
                    onClick={async () => {
                      await startCamera(c.id);
                      refresh();
                    }}
                    className="text-xs bg-green-600 hover:bg-green-500 rounded px-3 py-1"
                  >
                    Start
                  </button>
                )}
              </div>
            </div>

            {viewingId === c.id && c.is_active && (
              <img
                src={videoFeedUrl(c.id)}
                alt={`${c.name} live feed`}
                className="mt-3 w-full rounded border border-gray-700"
              />
            )}
          </div>
        ))}
        {cameras.length === 0 && (
          <p className="text-sm text-gray-500">No cameras added yet.</p>
        )}
      </div>
    </div>
  );
}
