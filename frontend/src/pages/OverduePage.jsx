import { useEffect, useState } from "react";
import { api } from "../api";
import { PageHeader } from "../components/PageHeader";
import { formatDateShort } from "../utils/date";
import { onRefreshNeeded } from "../hooks/useRefresh";

export default function OverduePage() {
  const [records, setRecords] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const fetchRecords = () => {
    setLoading(true);
    api.overdue()
      .then((res) => setRecords(res || []))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchRecords();
  }, []);

  useEffect(() => {
    // Register for refresh signals
    const unsubscribe = onRefreshNeeded(fetchRecords);
    return () => unsubscribe();
  }, []);

  return (
    <div className="page-card">
      <PageHeader title="Overdue Books" subtitle="All overdue borrowings with days late." />

      {loading ? (
        <p className="notice">Loading overdue records...</p>
      ) : error ? (
        <p className="error">{error}</p>
      ) : records.length === 0 ? (
        <p className="empty">No overdue books.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Book</th>
              <th>User</th>
              <th>Borrowed</th>
              <th>Due</th>
              <th>Days Late</th>
            </tr>
          </thead>
          <tbody>
            {records.map((r) => {
              const today = new Date();
              const dueDate = new Date(r.due_date);
              const daysLate = Math.max(0, Math.floor((today - dueDate) / (1000 * 60 * 60 * 24)));
              return (
                <tr key={r.id} className="row-overdue">
                  <td>{r.title}</td>
                  <td>{r.borrower_name}</td>
                  <td>{formatDateShort(r.borrow_date)}</td>
                  <td>{formatDateShort(r.due_date)}</td>
                  <td><strong>{daysLate} day{daysLate !== 1 ? 's' : ''}</strong></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
