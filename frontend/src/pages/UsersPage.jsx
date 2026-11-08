import { useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../hooks/useAuth";

export default function UsersPage() {
  const { user: currentUser } = useAuth();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [formData, setFormData] = useState({
    username: "",
    email: "",
    password: "",
    passwordConfirm: "",
  });
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    loadUsers();
  }, []);

  const loadUsers = async () => {
    try {
      setLoading(true);
      const response = await api.get("/users");
      setUsers(response.data);
    } catch (err) {
      setError("Failed to load users");
    } finally {
      setLoading(false);
    }
  };

  const handleCreateUser = async (e) => {
    e.preventDefault();
    setError("");
    setSuccess("");

    if (formData.password !== formData.passwordConfirm) {
      setError("Passwords do not match");
      return;
    }

    if (!formData.username || !formData.email || !formData.password) {
      setError("All fields are required");
      return;
    }

    try {
      await api.post("/users", {
        username: formData.username,
        email: formData.email,
        password: formData.password,
      });
      setSuccess(`User "${formData.username}" created successfully`);
      setFormData({ username: "", email: "", password: "", passwordConfirm: "" });
      setShowCreateModal(false);
      await loadUsers();
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to create user");
    }
  };

  const handleToggleUser = async (userId, isActive) => {
    try {
      await api.put(`/users/${userId}`, { is_active: !isActive });
      await loadUsers();
    } catch (err) {
      setError("Failed to update user");
    }
  };

  const handleResetPassword = async (userId, username) => {
    const newPassword = prompt(`Enter new password for "${username}":`);
    if (!newPassword) return;

    try {
      await api.put(`/users/${userId}/password`, { password: newPassword });
      setSuccess(`Password reset for "${username}"`);
      await loadUsers();
    } catch (err) {
      setError("Failed to reset password");
    }
  };

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">User Management</h1>
        <button
          onClick={() => setShowCreateModal(true)}
          className="bg-blue-600 hover:bg-blue-500 rounded px-4 py-2 text-sm font-medium"
        >
          + Create User
        </button>
      </div>

      {error && <div className="bg-red-900 text-red-200 p-3 rounded">{error}</div>}
      {success && <div className="bg-green-900 text-green-200 p-3 rounded">{success}</div>}

      {loading ? (
        <div className="text-gray-400">Loading...</div>
      ) : (
        <div className="bg-gray-900 border border-gray-700 rounded overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-800">
              <tr>
                <th className="px-6 py-3 text-left text-sm font-medium">Username</th>
                <th className="px-6 py-3 text-left text-sm font-medium">Email</th>
                <th className="px-6 py-3 text-left text-sm font-medium">Role</th>
                <th className="px-6 py-3 text-left text-sm font-medium">Status</th>
                <th className="px-6 py-3 text-left text-sm font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.id} className="border-t border-gray-700 hover:bg-gray-800/50">
                  <td className="px-6 py-4 text-sm">{user.username}</td>
                  <td className="px-6 py-4 text-sm">{user.email}</td>
                  <td className="px-6 py-4 text-sm">
                    <span className="bg-gray-700 px-2 py-1 rounded text-xs uppercase">
                      {user.role}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-sm">
                    <span className={user.is_active ? "text-green-400" : "text-red-400"}>
                      {user.is_active ? "Active" : "Disabled"}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-sm space-x-2">
                    {user.username !== "admin" && user.id !== currentUser?.id && (
                      <button
                        onClick={() => handleToggleUser(user.id, user.is_active)}
                        className="text-yellow-400 hover:text-yellow-300"
                      >
                        {user.is_active ? "Disable" : "Activate"}
                      </button>
                    )}
                    <button
                      onClick={() => handleResetPassword(user.id, user.username)}
                      className="text-orange-400 hover:text-orange-300"
                    >
                      Reset Pass
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Create User Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6 w-full max-w-md space-y-4">
            <h2 className="text-xl font-bold">Create User</h2>

            <form onSubmit={handleCreateUser} className="space-y-4">
              <div>
                <label className="text-xs text-gray-400">Username *</label>
                <input
                  type="text"
                  value={formData.username}
                  onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                  className="w-full bg-gray-800 rounded px-3 py-2 text-sm mt-1 focus:outline-none focus:ring-2 focus:ring-blue-600"
                />
              </div>

              <div>
                <label className="text-xs text-gray-400">Email *</label>
                <input
                  type="email"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  className="w-full bg-gray-800 rounded px-3 py-2 text-sm mt-1 focus:outline-none focus:ring-2 focus:ring-blue-600"
                />
              </div>

              <div>
                <label className="text-xs text-gray-400">Password *</label>
                <input
                  type="password"
                  value={formData.password}
                  onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                  className="w-full bg-gray-800 rounded px-3 py-2 text-sm mt-1 focus:outline-none focus:ring-2 focus:ring-blue-600"
                />
              </div>

              <div>
                <label className="text-xs text-gray-400">Confirm Password *</label>
                <input
                  type="password"
                  value={formData.passwordConfirm}
                  onChange={(e) => setFormData({ ...formData, passwordConfirm: e.target.value })}
                  className="w-full bg-gray-800 rounded px-3 py-2 text-sm mt-1 focus:outline-none focus:ring-2 focus:ring-blue-600"
                />
              </div>

              <div className="bg-gray-800 p-3 rounded">
                <p className="text-xs text-gray-400">Role: <strong>USER</strong></p>
              </div>

              {error && <p className="text-sm text-red-400">{error}</p>}

              <div className="flex gap-2 pt-4">
                <button
                  type="button"
                  onClick={() => {
                    setShowCreateModal(false);
                    setError("");
                    setFormData({ username: "", email: "", password: "", passwordConfirm: "" });
                  }}
                  className="flex-1 bg-gray-700 hover:bg-gray-600 rounded px-3 py-2 text-sm"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="flex-1 bg-blue-600 hover:bg-blue-500 rounded px-3 py-2 text-sm font-medium"
                >
                  Create User
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
