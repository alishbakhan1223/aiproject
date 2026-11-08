import { useEffect, useState, useCallback } from "react";
import { getKnownFaces } from "../api";
import RegisterFace from "../components/RegisterFace";

export default function PersonsPage() {
  const [knownFaces, setKnownFaces] = useState([]);

  const refresh = useCallback(async () => {
    setKnownFaces(await getKnownFaces());
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <div className="p-6 space-y-4 max-w-3xl">
      {/* Rule 1: 48-Hour Revert Lock Prominent Banner */}
      <div className="rounded-xl border-2 border-red-500/80 bg-red-950/40 p-4 shadow-lg text-red-200 flex items-start gap-3">
        <span className="text-2xl leading-none select-none text-red-400">⚠️</span>
        <div className="space-y-1">
          <p className="font-extrabold text-lg sm:text-xl text-red-300 leading-snug">
            If an unknown was mapped by mistake, you can revert it only within 48 hours. After 48 hours, no changes are possible.
          </p>
          <p className="text-xs text-red-400/80">
            Rule 1 Security Policy: Reverting to unknown, removing photos, or deleting mapped persons is permanently locked after 48 hours.
          </p>
        </div>
      </div>

      <header>
        <h1 className="text-xl font-bold">Registered Persons</h1>
        <p className="text-sm text-gray-400">Manage known members eligible for face recognition</p>
      </header>
      <RegisterFace onRegistered={refresh} knownFaces={knownFaces} />
    </div>
  );
}
