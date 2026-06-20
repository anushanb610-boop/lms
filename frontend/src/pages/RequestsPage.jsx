import { useEffect, useState } from "react";
import { api } from "../api";
import { PageHeader } from "../components/PageHeader";
import { triggerRefreshForAll } from "../hooks/useRefresh";

export default function RequestsPage({ showToast }) {
  const [requests, setRequests] = useState([]);
  const [error, setError] = useState("");

  const load = () => {
    setError("");
    api.requests().then(setRequests).catch((e) => setError(e.message));
  };

  useEffect(() => {
    load();
  }, []);

  const act = async (recordId, action) => {
    try {
      if (action === "approve") await api.approveRequest(recordId);
      if (action === "reject") await api.rejectRequest(recordId);
      showToast(`Request ${action}d successfully.`, "success");
      load();
      // Trigger refresh for borrowed books page
      triggerRefreshForAll();
    } catch (e) {
      setError(e.message);
      showToast(e.message, "error");
    }
  };

  return (
    <div className="page-card">
      <PageHeader title="Pending Requests" subtitle="Review borrow requests and take action." />
      {error && <p className="error">{error}</p>}
      {requests.length === 0 ? (
        <p className="empty">No pending requests.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Request ID</th>
              <th>User Name</th>
              <th>Book Title</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {requests.map((r) => (
              <tr key={r.id}>
                <td>#{r.id}</td>
                <td>{r.borrower_name}</td>
                <td>{r.title}</td>
                <td><span className="badge">{r.status}</span></td>
                <td>
                  <button className="btn-action primary" onClick={() => act(r.id, "approve")}>✓ Approve</button>
                  <button className="btn-action danger" onClick={() => act(r.id, "reject")}>✕ Reject</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
