import { useEffect, useState, useCallback } from "react";
import { getEvents, getStatistics, getCameras } from "../api";
import Stats from "../components/Stats";
import EventsTable from "../components/EventsTable";
import LiveFeed from "../components/LiveFeed";

export default function DashboardPage() {
  const [events, setEvents] = useState([]);
  const [stats, setStats] = useState(null);
  const [cameras, setCameras] = useState([]);

  const refresh = useCallback(async () => {
    const [e, s, c] = await Promise.all([getEvents(), getStatistics(), getCameras()]);
    setEvents(e.slice(0, 10));
    setStats(s);
    setCameras(c);
  }, []);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 5000);
    return () => clearInterval(interval);
  }, [refresh]);

  return (
    <div className="p-6 space-y-6">
      <header>
        <h1 className="text-xl font-bold">Live Monitoring Dashboard</h1>
        <p className="text-sm text-gray-400">Real-time overview of all cameras and activity</p>
      </header>

      <Stats stats={stats} />
      <LiveFeed cameras={cameras} refresh={refresh} />

      <div>
        <h2 className="font-semibold mb-3">Recent Events</h2>
        <EventsTable events={events} />
      </div>
    </div>
  );
}
