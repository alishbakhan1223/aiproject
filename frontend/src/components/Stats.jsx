export default function Stats({ stats }) {
  if (!stats) return null;

  const cards = [
    { label: "Total Events", value: stats.total_events },
    { label: "Weapons Detected", value: stats.weapon_events || 0, warn: true },
    { label: "Unknown Persons", value: stats.unknown_person_events, warn: true },
    { label: "Restricted Objects", value: stats.restricted_object_events, warn: true },
    { label: "Forensic Confirmations", value: stats.forensic_confirmations, warn: true },
    { label: "Known Persons", value: stats.known_person_events },
    { label: "Registered Faces", value: stats.total_known_faces },
    { label: "Active Cameras", value: stats.active_cameras },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-4">
      {cards.map((c) => (
        <div
          key={c.label}
          className={`rounded-xl p-4 border ${
            c.warn ? "border-red-500/40 bg-red-950/30" : "border-gray-700 bg-gray-900"
          }`}
        >
          <p className="text-xs text-gray-400">{c.label}</p>
          <p className="text-2xl font-semibold mt-1">{c.value}</p>
        </div>
      ))}
    </div>
  );
}
