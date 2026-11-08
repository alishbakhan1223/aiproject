import { useEffect, useState, useCallback } from "react";
import { getStatistics } from "../api";
import Stats from "../components/Stats";

export default function StatsPage() {
  const [stats, setStats] = useState(null);

  const refresh = useCallback(async () => {
    setStats(await getStatistics());
  }, []);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 5000);
    return () => clearInterval(interval);
  }, [refresh]);

  return (
    <div className="p-6 space-y-4">
      <header>
        <h1 className="text-xl font-bold">Statistics</h1>
        <p className="text-sm text-gray-400">Summary counts across all cameras and events</p>
      </header>
      <Stats stats={stats} />
    </div>
  );
}
