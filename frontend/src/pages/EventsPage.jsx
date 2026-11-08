import { useEffect, useState, useCallback } from "react";
import { getEvents } from "../api";
import EventsTable from "../components/EventsTable";

const FILTERS = [
  { value: "", label: "All" },
  { value: "weapon_detected", label: "Weapon Detections" },
  { value: "known_person", label: "Known Person" },
  { value: "unknown_person", label: "Unknown Person" },
  { value: "restricted_object", label: "Restricted Object" },
  { value: "forensic_confirmation", label: "Forensic Confirmation" },
];

export default function EventsPage() {
  const [events, setEvents] = useState([]);
  const [filter, setFilter] = useState("");

  const refresh = useCallback(async () => {
    setEvents(await getEvents(filter || undefined));
  }, [filter]);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 5000);
    return () => clearInterval(interval);
  }, [refresh]);

  return (
    <div className="p-6 space-y-4">
      <header>
        <h1 className="text-xl font-bold">All Events</h1>
        <p className="text-sm text-gray-400">Complete log of everything detected, across all cameras</p>
      </header>

      <div className="flex gap-2">
        {FILTERS.map((f) => (
          <button
            key={f.value}
            onClick={() => setFilter(f.value)}
            className={`text-sm px-3 py-1.5 rounded ${
              filter === f.value ? "bg-blue-600" : "bg-gray-800 text-gray-400"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      <EventsTable events={events} />
    </div>
  );
}
