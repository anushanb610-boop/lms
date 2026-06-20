import { useEffect, useState } from "react";
import { api } from "../api";
import { PageHeader } from "../components/PageHeader";
import { formatDateShort } from "../utils/date";
import { useAuth } from "../hooks/useAuth";
import { onRefreshNeeded } from "../hooks/useRefresh";

export default function BorrowedPage({ mode }) {
  const [records, setRecords] = useState([]);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const { user } = useAuth();

  const fetchRecords = () => {
    setLoading(true);
    const loader = mode === "active" ? api.active() : api.history();
    loader
      .then(setRecords)
      .catch((e) => setMessage(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchRecords();
  }, [mode]);

  useEffect(() => {
    // Register for refresh signals
    const unsubscribe = onRefreshNeeded(fetchRecords);
    return () => unsubscribe();
  }, [mode]);

  const ret = async (id) => {
    try {
      await api.returnBook(id);
      setMessage("Book returned successfully.");
      const res = await api.active();
      setRecords(res);
    } catch (e) {
      setMessage(e.message);
    }
  };

  // Calculate status for each record
  const getRecordStatus = (record) => {
    if (mode === "history") return null;
    
    if (record.returned_date) return "returned";
    if (!record.due_date) return "borrowed";
    
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const dueDate = new Date(record.due_date);
    dueDate.setHours(0, 0, 0, 0);
    
    if (today > dueDate) {
      const daysOverdue = Math.floor((today - dueDate) / (1000 * 60 * 60 * 24));
      return { type: "overdue", days: daysOverdue };
    }
    return "borrowed";
  };

  const getStatusBadge = (status) => {
    if (status === "borrowed") {
      return <span className="status-badge status-borrowed">BORROWED</span>;
    }
    if (status === "returned") {
      return <span className="status-badge status-returned">RETURNED</span>;
    }
    if (status && typeof status === "object" && status.type === "overdue") {
      return (
        <span className="status-badge status-overdue">
          OVERDUE ({status.days} days)
        </span>
      );
    }
    return <span className="status-badge status-default">{status}</span>;
  };

  const overdueCount = mode === "active" 
    ? records.filter(r => {
        const status = getRecordStatus(r);
        return status && typeof status === "object" && status.type === "overdue";
      }).length
    : 0;

  return (
    <div className="page-card borrowed-page-card">
      <PageHeader
        title={mode === "active" ? "📚 Currently Borrowed" : "📖 Return History"}
      />

      {message && <div className="alert alert-info">{message}</div>}

      {loading ? (
        <div className="loading-container">
          <div className="spinner"></div>
          <p>Loading records...</p>
        </div>
      ) : records.length === 0 ? (
        <div className="empty-state">
          <p className="empty-icon">📚</p>
          <p className="empty-title">No records available</p>
          <p className="empty-hint">
            {mode === "active" ? "You haven't borrowed any books yet." : "Your return history is empty."}
          </p>
        </div>
      ) : (
        <>
          <div className="records-summary">
            Total: <strong>{records.length}</strong> book{records.length !== 1 ? "s" : ""}
            {mode === "active" && overdueCount > 0 && (
              <span className="overdue-count">
                • <strong>{overdueCount}</strong> overdue
              </span>
            )}
          </div>

          <div className="borrowed-table-wrapper">
            <table className="borrowed-table">
              <thead className="table-header-sticky">
                <tr>
                  {user?.role === "user" ? (
                    <th className="col-serial">Serial No.</th>
                  ) : (
                    <th className="col-borrower">Borrower Name</th>
                  )}
                  <th className="col-book">Book Title</th>
                  <th className="col-dates">Borrowed</th>
                  <th className="col-dates">Due Date</th>
                  {mode === "history" ? (
                    <th className="col-dates">Returned</th>
                  ) : (
                    <th className="col-status">Status</th>
                  )}
                  {mode === "active" && user?.role === "user" && (
                    <th className="col-actions">Action</th>
                  )}
                </tr>
              </thead>
              <tbody>
                {records.map((record, index) => {
                  const status = getRecordStatus(record);
                  const isOverdue = status && typeof status === "object" && status.type === "overdue";
                  return (
                    <tr 
                      key={record.id} 
                      className={`table-row ${isOverdue ? "overdue" : ""}`}
                    >
                      {user?.role === "user" ? (
                        <td className="col-serial">
                          <span className="serial-number">{index + 1}</span>
                        </td>
                      ) : (
                        <td className="col-borrower">
                          <span className="borrower-name">{record.borrower_name}</span>
                        </td>
                      )}
                      <td className="col-book">
                        <span className="book-title">{record.title}</span>
                      </td>
                      <td className="col-dates">
                        <span className="date-badge">{formatDateShort(record.borrow_date)}</span>
                      </td>
                      <td className="col-dates">
                        <span className={`date-badge ${isOverdue ? "overdue" : ""}`}>
                          {formatDateShort(record.due_date)}
                        </span>
                      </td>
                      {mode === "history" ? (
                        <td className="col-dates">
                          <span className="date-badge">{formatDateShort(record.returned_date)}</span>
                        </td>
                      ) : (
                        <td className="col-status">
                          {getStatusBadge(status)}
                        </td>
                      )}
                      {mode === "active" && user?.role === "user" && (
                        <td className="col-actions">
                          {!record.returned_date && (
                            <button 
                              className="btn-return"
                              onClick={() => ret(record.id)}
                              title="Return this book"
                            >
                              ↩ Return
                            </button>
                          )}
                          {record.returned_date && (
                            <span className="action-none">—</span>
                          )}
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

