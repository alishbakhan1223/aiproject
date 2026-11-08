import { snapshotUrl } from "../api";

const badgeColor = {
  unknown_person: "bg-red-600",
  restricted_object: "bg-orange-600",
  known_person: "bg-green-600",
  forensic_confirmation: "bg-purple-600",
  weapon_detected: "bg-rose-700 text-rose-100 font-bold",
};

// in_zone: true = inside, false = outside, null/undefined = zone off (no zone configured)
function zoneLabel(inZone) {
  if (inZone === null || inZone === undefined) {
    return { text: "zone off", cls: "text-gray-500" };
  }
  return inZone
    ? { text: "inside", cls: "text-red-400 font-medium" }
    : { text: "outside", cls: "text-gray-400" };
}

export default function EventsTable({ events }) {
  return (
    <div className="rounded-xl border border-gray-700 bg-gray-900 overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-gray-800 text-gray-400">
          <tr>
            <th className="text-left p-3">Snapshot</th>
            <th className="text-left p-3">Type</th>
            <th className="text-left p-3">Camera</th>
            <th className="text-left p-3">Detail</th>
            <th className="text-left p-3">Zone</th>
            <th className="text-left p-3">Confidence</th>
            <th className="text-left p-3">Time</th>
          </tr>
        </thead>
        <tbody>
          {events.map((e) => {
            const zone = zoneLabel(e.in_zone);
            return (
              <tr key={e.id} className="border-t border-gray-800">
                <td className="p-3">
                  {e.snapshot_path ? (
                    <img
                      src={snapshotUrl(e.snapshot_path)}
                      alt="snapshot"
                      className="w-16 h-16 object-cover rounded"
                    />
                  ) : (
                    "—"
                  )}
                </td>
                <td className="p-3">
                  <span
                    className={`px-2 py-1 rounded text-xs ${badgeColor[e.event_type] || "bg-gray-600"
                      }`}
                  >
                    {e.event_type.replace(/_/g, " ")}
                  </span>
                </td>
                <td className="p-3">{e.camera_name}</td>
                <td className="p-3">{e.person_name || e.object_name || "-"}</td>
                <td className={`p-3 text-xs ${zone.cls}`}>{zone.text}</td>
                <td className="p-3">
                  {e.confidence != null ? `${(e.confidence * 100).toFixed(0)}%` : "-"}
                </td>
                <td className="p-3 text-gray-400">
                  {new Date(e.timestamp).toLocaleString()}
                </td>
              </tr>
            );
          })}
          {events.length === 0 && (
            <tr>
              <td colSpan={7} className="p-6 text-center text-gray-500">
                No events yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}