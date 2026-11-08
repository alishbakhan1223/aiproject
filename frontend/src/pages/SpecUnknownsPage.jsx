// FILE: frontend/src/pages/SpecUnknownsPage.jsx
import { useEffect, useState, useCallback } from "react";
import { api } from "../api";

const STATUS_STYLE = {
    Successful: "bg-green-900/80 text-green-300 border border-green-700",
    Unsuccessful: "bg-red-900/80 text-red-300 border border-red-700",
    Pending: "bg-yellow-900/80 text-yellow-300 border border-yellow-700",
};

// Auto-formats MM-DD-YY while typing: "100726" -> "10-07-26"
function maskDate(raw) {
    const d = raw.replace(/\D/g, "").slice(0, 6);
    if (d.length <= 2) return d;
    if (d.length <= 4) return `${d.slice(0, 2)}-${d.slice(2)}`;
    return `${d.slice(0, 2)}-${d.slice(2, 4)}-${d.slice(4)}`;
}

function isValidDate(s) {
    const m = /^(\d{2})-(\d{2})-(\d{2})$/.exec(s);
    if (!m) return false;
    const mm = Number(m[1]);
    const dd = Number(m[2]);
    return mm >= 1 && mm <= 12 && dd >= 1 && dd <= 31;
}

export default function SpecUnknownsPage() {
    const [rows, setRows] = useState([]);
    const [locations, setLocations] = useState([]);
    const [location, setLocation] = useState("");
    const [date, setDate] = useState(""); // MM-DD-YY
    const [error, setError] = useState("");

    const dateTyped = date.length > 0;
    const dateOk = isValidDate(date);

    useEffect(() => {
        api
            .get("/spec-unknowns/locations")
            .then((r) => setLocations(r.data))
            .catch(() => { });
    }, []);

    const refresh = useCallback(async () => {
        // Do not call API for incomplete or invalid date
        if (dateTyped && !dateOk) return;
        try {
            const params = {};
            if (location) params.location_code = location;
            if (dateOk) params.date = date;
            const r = await api.get("/spec-unknowns", { params });
            setRows(r.data);
            setError("");
        } catch (e) {
            setError("Could not load data. Please check that the backend is running.");
        }
    }, [location, date, dateTyped, dateOk]);

    useEffect(() => {
        refresh();
        const t = setInterval(refresh, 5000);
        return () => clearInterval(t);
    }, [refresh]);

    return (
        <div className="p-6 space-y-4">
            {/* Rule 2: 30-Day Window Banner */}
            <div className="rounded-xl border-2 border-red-500/80 bg-red-950/40 p-3.5 shadow-lg text-red-200 flex items-center gap-3">
                <span className="text-xl select-none text-red-400">ℹ️</span>
                <p className="text-xs sm:text-sm">
                    <span className="font-bold text-red-300">30-Day Mapping Window:</span> Unmapped unknowns must be mapped within 30 days before being automatically purged. Mappings completed within 48h are Successful; unmapped detections remain Pending for 48h, then become Unsuccessful.
                </p>
            </div>

            <header>
                <h1 className="text-xl font-bold">Unknown IDs</h1>
                <p className="text-sm text-gray-400">
                    Unknown detections with their Smart IDs. Filter by location and date (MM-DD-YY).
                </p>
            </header>

            <div className="flex flex-wrap gap-3 items-center">
                <select
                    value={location}
                    onChange={(e) => setLocation(e.target.value)}
                    className="bg-gray-800 rounded px-3 py-1.5 text-sm"
                >
                    <option value="">All Locations</option>
                    {locations.map((l) => (
                        <option key={l.location_code} value={l.location_code}>
                            {l.location_name} ({l.location_code})
                        </option>
                    ))}
                </select>

                <input
                    type="text"
                    inputMode="numeric"
                    placeholder="MM-DD-YY"
                    value={date}
                    onChange={(e) => setDate(maskDate(e.target.value))}
                    className={`bg-gray-800 rounded px-3 py-1.5 text-sm w-32 ${dateTyped && !dateOk ? "border border-red-600" : ""
                        }`}
                />

                <button
                    onClick={() => {
                        setLocation("");
                        setDate("");
                    }}
                    className="bg-gray-800 hover:bg-gray-700 rounded px-3 py-1.5 text-sm"
                >
                    All (clear filters)
                </button>

                <span className="text-sm text-gray-500">{rows.length} records</span>
            </div>

            {dateTyped && !dateOk && (
                <p className="text-xs text-red-400">Enter the full date as MM-DD-YY (for example 10-07-26).</p>
            )}
            {error && <p className="text-sm text-red-400">{error}</p>}

            <div className="overflow-x-auto rounded border border-gray-800">
                <table className="w-full text-sm">
                    <thead className="bg-gray-900 text-gray-400 text-left">
                        <tr>
                            <th className="px-3 py-2">Unknown ID</th>
                            <th className="px-3 py-2">Company</th>
                            <th className="px-3 py-2">Location</th>
                            <th className="px-3 py-2">Camera</th>
                            <th className="px-3 py-2">Date (MM-DD-YY)</th>
                            <th className="px-3 py-2">Time</th>
                            <th className="px-3 py-2">Map within</th>
                            <th className="px-3 py-2">Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows.length === 0 && (
                            <tr>
                                <td colSpan={8} className="px-3 py-6 text-center text-gray-500">
                                    No records found.
                                </td>
                            </tr>
                        )}
                        {rows.map((r) => {
                            const isExpiringSoon = r.mapping_days_left !== undefined && r.mapping_days_left !== null && r.mapping_days_left <= 3;
                            const isMapped = r.map_within === "Mapped";

                            return (
                                <tr key={r.unknown_id} className="border-t border-gray-800">
                                    <td className="px-3 py-2 font-mono">{r.unknown_id}</td>
                                    <td className="px-3 py-2">{r.company_name}</td>
                                    <td className="px-3 py-2">{r.location_name}</td>
                                    <td className="px-3 py-2">{r.camera_code}</td>
                                    <td className="px-3 py-2">{r.date_shown}</td>
                                    <td className="px-3 py-2">{r.time_shown}</td>
                                    <td className="px-3 py-2">
                                        {isMapped ? (
                                            <span className="text-xs text-gray-400 italic">Mapped</span>
                                        ) : (
                                            <span
                                                className={`px-2 py-0.5 rounded text-xs font-semibold ${
                                                    isExpiringSoon
                                                        ? "bg-red-950 text-red-300 border border-red-700 font-bold"
                                                        : "bg-gray-800 text-gray-300"
                                                }`}
                                            >
                                                {r.map_within || "—"}
                                            </span>
                                        )}
                                    </td>
                                    <td className="px-3 py-2">
                                        {r.status ? (
                                            <span
                                                className={`px-2 py-0.5 rounded text-xs ${STATUS_STYLE[r.status] || "bg-gray-800"
                                                    }`}
                                            >
                                                {r.status}
                                            </span>
                                        ) : (
                                            <span className="text-gray-500">Not checked</span>
                                        )}
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
