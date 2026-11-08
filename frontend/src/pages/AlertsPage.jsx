import { useEffect, useState, useCallback } from "react";
import { getAlerts, getTelegramStatus, sendTelegramTest } from "../api";
import EventsTable from "../components/EventsTable";

export default function AlertsPage() {
  const [alerts, setAlerts] = useState([]);
  const [tgStatus, setTgStatus] = useState(null);
  const [testingTg, setTestingTg] = useState(false);
  const [testResult, setTestResult] = useState("");

  const refresh = useCallback(async () => {
    setAlerts(await getAlerts());
  }, []);

  useEffect(() => {
    refresh();
    getTelegramStatus().then(setTgStatus).catch(() => {});
    const interval = setInterval(refresh, 5000);
    return () => clearInterval(interval);
  }, [refresh]);

  const handleTestTelegram = async () => {
    setTestingTg(true);
    setTestResult("");
    try {
      const res = await sendTelegramTest("🚨 CCTV Test Alert: Telegram integration is working!");
      if (res.result?.ok) {
        setTestResult("✅ Message delivered to Telegram!");
      } else if (res.result?.skipped) {
        setTestResult("⚠️ Telegram bot token/chat ID not configured in .env");
      } else {
        setTestResult(`❌ Error: ${JSON.stringify(res.result?.description || res.result)}`);
      }
    } catch (err) {
      setTestResult("❌ Failed to send request: " + (err.response?.data?.detail || err.message));
    } finally {
      setTestingTg(false);
    }
  };

  return (
    <div className="p-6 space-y-4">
      <header className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold">Alerts</h1>
          <p className="text-sm text-gray-400">
            Unknown persons, restricted objects, forensic confirmations, and weapons
          </p>
        </div>
        <div className="flex items-center gap-3">
          {tgStatus && (
            <span
              className={`text-xs px-2.5 py-1 rounded-full border ${
                tgStatus.configured
                  ? "bg-blue-900/40 text-blue-300 border-blue-700"
                  : "bg-gray-800 text-gray-400 border-gray-700"
              }`}
            >
              Telegram: {tgStatus.configured ? "Configured" : "Not Set"}
            </span>
          )}
          <button
            onClick={handleTestTelegram}
            disabled={testingTg}
            className="text-xs bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-medium px-3 py-1.5 rounded transition shadow-sm"
          >
            {testingTg ? "Sending..." : "Test Telegram Alert"}
          </button>
        </div>
      </header>

      {testResult && (
        <div className="p-3 text-sm rounded bg-gray-800 border border-gray-700">
          {testResult}
        </div>
      )}

      <EventsTable events={alerts} />
    </div>
  );
}
