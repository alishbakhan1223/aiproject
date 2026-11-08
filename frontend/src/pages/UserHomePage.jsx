import { Link } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

export default function UserHomePage() {
  const { user } = useAuth();

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 p-6">
      <div className="max-w-2xl mx-auto space-y-6">
        {/* Welcome Header */}
        <div className="bg-gray-900 border border-gray-700 rounded-lg p-8 text-center space-y-3">
          <h1 className="text-3xl font-bold">Welcome, {user?.username}!</h1>
          <p className="text-gray-400">You have access to the People Operations module</p>
        </div>

        {/* Available Operations */}
        <div className="space-y-4">
          <h2 className="text-xl font-bold">People Operations</h2>

          <Link
            to="/user/people/add"
            className="block bg-gray-900 border border-gray-700 hover:border-blue-600 rounded-lg p-6 transition space-y-2"
          >
            <h3 className="font-bold text-lg flex items-center gap-2">
              <span className="text-2xl">➕</span>
              Add Known Person
            </h3>
            <p className="text-sm text-gray-400">
              Register a new person with face recognition. Provide a name and face image for identification.
            </p>
          </Link>

          <Link
            to="/user/people/promote"
            className="block bg-gray-900 border border-gray-700 hover:border-blue-600 rounded-lg p-6 transition space-y-2"
          >
            <h3 className="font-bold text-lg flex items-center gap-2">
              <span className="text-2xl">⬆️</span>
              Promote Unknown → Known
            </h3>
            <p className="text-sm text-gray-400">
              Convert an unidentified person detection into a known person profile with full details.
            </p>
          </Link>
        </div>

        {/* Info Card */}
        <div className="bg-gray-900 border border-gray-700 rounded-lg p-6 space-y-3">
          <h3 className="font-bold">About Your Role</h3>
          <p className="text-sm text-gray-400">
            As a <strong>User</strong>, you have limited access to the AICCTV system focused on people operations. 
            You can add known individuals and promote unknown detections to known people. 
            Administrative functions like camera management, zone configuration, and user management are not available in your workspace.
          </p>
        </div>
      </div>
    </div>
  );
}
