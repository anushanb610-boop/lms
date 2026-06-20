import { useEffect, useState } from "react";
import { api } from "../api";
import { PageHeader } from "../components/PageHeader";
import { formatDateShort } from "../utils/date";
import { useAuth } from "../hooks/useAuth";
import { onRefreshNeeded } from "../hooks/useRefresh";

export default function BooksPage({ canBorrow = true, showToast }) {
  const { user } = useAuth();
  const [subjects, setSubjects] = useState([]);
  const [subject, setSubject] = useState("");
  const [books, setBooks] = useState([]);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);
  const [showEditForm, setShowEditForm] = useState(false);
  const [viewMode, setViewMode] = useState("cards");
  const [formData, setFormData] = useState({ title: "", author: "", subject: "", total_copies: 1 });
  const [editingBook, setEditingBook] = useState(null);
  const [editFormData, setEditFormData] = useState({ title: "", author: "", subject: "", available_copies: 0, total_copies: 0 });
  const [submitting, setSubmitting] = useState(false);

  const loadBooks = () => {
    setLoading(true);
    setMessage("");
    api.books(subject)
      .then((data) => setBooks(data))
      .catch((e) => setMessage(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    api.subjects().then(setSubjects).catch(() => {});
  }, []);

  useEffect(() => {
    loadBooks();
  }, [subject]);

  useEffect(() => {
    // Register for refresh signals to update book copies
    const unsubscribe = onRefreshNeeded(() => {
      loadBooks();
    });
    return () => unsubscribe();
  }, [subject]);

  const borrowBook = async (book) => {
    setMessage("");
    try {
      await api.borrow(book.id);
      const msg = `Request sent for "${book.title}".`;
      setMessage(msg);
      if (showToast) showToast(msg, "success");
      loadBooks();
    } catch (e) {
      setMessage(e.message);
      if (showToast) showToast(e.message, "error");
    }
  };

  const handleAddBook = async (e) => {
    e.preventDefault();
    setMessage("");
    setSubmitting(true);
    try {
      if (!formData.title || !formData.author || !formData.subject) {
        setMessage("Title, author, and subject are required.");
        setSubmitting(false);
        return;
      }
      await api.createBook(formData.title, formData.author, formData.subject, parseInt(formData.total_copies) || 1);
      setMessage("Book added successfully.");
      if (showToast) showToast("Book added successfully.", "success");
      setFormData({ title: "", author: "", subject: "", total_copies: 1 });
      setShowAddForm(false);
      loadBooks();
    } catch (e) {
      setMessage(e.message);
      if (showToast) showToast(e.message, "error");
    } finally {
      setSubmitting(false);
    }
  };

  const handleEditBook = (book) => {
    setEditingBook(book);
    setEditFormData({ 
      title: book.title, 
      author: book.author, 
      subject: book.subject,
      available_copies: book.available_copies || 0,
      total_copies: book.total_copies || 0
    });
    setShowEditForm(true);
  };

  const handleSaveEdit = async (e) => {
    e.preventDefault();
    if (!editingBook) return;
    setMessage("");
    setSubmitting(true);
    try {
      if (!editFormData.title || !editFormData.author || !editFormData.subject) {
        setMessage("Title, author, and subject are required.");
        setSubmitting(false);
        return;
      }
      
      const total = parseInt(editFormData.total_copies) || 0;
      const available = parseInt(editFormData.available_copies) || 0;
      
      if (total < 0) {
        setMessage("Total copies cannot be negative.");
        setSubmitting(false);
        return;
      }
      if (available < 0) {
        setMessage("Available copies cannot be negative.");
        setSubmitting(false);
        return;
      }
      if (available > total) {
        setMessage("Available copies cannot exceed total copies.");
        setSubmitting(false);
        return;
      }
      const borrowed = editingBook.borrowed_copies || 0;
      if (total < borrowed) {
        setMessage(`Total copies cannot be less than borrowed copies (${borrowed}).`);
        setSubmitting(false);
        return;
      }
      
      await api.updateBook(editingBook.id, editFormData.title, editFormData.author, editFormData.subject, available, total);
      setMessage("Book updated successfully.");
      if (showToast) showToast("Book updated successfully.", "success");
      setShowEditForm(false);
      setEditingBook(null);
      loadBooks();
    } catch (e) {
      setMessage(e.message);
      if (showToast) showToast(e.message, "error");
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeleteBook = async (bookId, title) => {
    if (!window.confirm(`Delete "${title}"?`)) return;
    setMessage("");
    try {
      await api.deleteBook(bookId);
      setMessage("Book deleted successfully.");
      if (showToast) showToast("Book deleted successfully.", "success");
      loadBooks();
    } catch (e) {
      setMessage(e.message);
      if (showToast) showToast(e.message, "error");
    }
  };

  const handleAddCopy = async (book) => {
    setMessage("");
    try {
      const newTotal = book.total_copies + 1;
      const newAvailable = (book.available_copies || 0) + 1;
      await api.updateBook(book.id, book.title, book.author, book.subject, newAvailable, newTotal);
      setMessage("Copy added successfully.");
      if (showToast) showToast("Copy added successfully.", "success");
      loadBooks();
    } catch (e) {
      setMessage(e.message);
      if (showToast) showToast(e.message, "error");
    }
  };

  const handleRemoveCopy = async (book) => {
    setMessage("");
    try {
      const borrowed = book.borrowed_copies || 0;
      const available = book.available_copies || 0;
      
      if (available <= 0) {
        setMessage("No available copies to remove.");
        if (showToast) showToast("No available copies to remove.", "error");
        return;
      }
      
      const newTotal = book.total_copies - 1;
      if (newTotal < borrowed) {
        setMessage(`Cannot remove: ${borrowed} copies are borrowed.`);
        if (showToast) showToast(`Cannot remove: ${borrowed} copies are borrowed.`, "error");
        return;
      }
      
      const newAvailable = available - 1;
      await api.updateBook(book.id, book.title, book.author, book.subject, newAvailable, newTotal);
      setMessage("Copy removed successfully.");
      if (showToast) showToast("Copy removed successfully.", "success");
      loadBooks();
    } catch (e) {
      setMessage(e.message);
      if (showToast) showToast(e.message, "error");
    }
  };

  return (
    <div className="page-card">
      <PageHeader
        title="Books"
      />

      <div className="books-toolbar-modern">
        <div className="filter-section">
          <label htmlFor="subject-filter" className="filter-label">Filter by Subject:</label>
          <select
            id="subject-filter"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            className="subject-dropdown"
          >
            <option value="">📚 All Subjects</option>
            {subjects.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>

        <div className="view-toggle">
          <button
            className={`view-btn ${viewMode === "cards" ? "active" : ""}`}
            onClick={() => setViewMode("cards")}
            title="Card view"
          >
            ⊞ Cards
          </button>
          <button
            className={`view-btn ${viewMode === "table" ? "active" : ""}`}
            onClick={() => setViewMode("table")}
            title="Table view"
          >
            ≡ Table
          </button>
        </div>

        {user?.role === "admin" && (
          <button className="primary btn-add-book" onClick={() => setShowAddForm(true)}>
            ➕ Add Book
          </button>
        )}
      </div>

      {/* Add Book Modal */}
      {showAddForm && (
        <div className="modal-overlay" onClick={() => setShowAddForm(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>Add New Book</h3>
            <form onSubmit={handleAddBook}>
              <div>
                <label>Title</label>
                <input
                  type="text"
                  value={formData.title}
                  onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                  placeholder="Book title"
                  required
                />
              </div>
              <div>
                <label>Author</label>
                <input
                  type="text"
                  value={formData.author}
                  onChange={(e) => setFormData({ ...formData, author: e.target.value })}
                  placeholder="Author name"
                  required
                />
              </div>
              <div>
                <label>Subject</label>
                <select
                  value={formData.subject}
                  onChange={(e) => setFormData({ ...formData, subject: e.target.value })}
                  required
                >
                  <option value="">Select subject</option>
                  {subjects.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </div>
              <div>
                <label>Total Copies</label>
                <input
                  type="number"
                  value={formData.total_copies}
                  onChange={(e) => setFormData({ ...formData, total_copies: e.target.value })}
                  min="1"
                  required
                />
              </div>
              <div style={{ display: "flex", gap: ".75rem", marginTop: "1rem" }}>
                <button type="submit" className="primary" disabled={submitting}>
                  {submitting ? "Adding..." : "Add Book"}
                </button>
                <button type="button" className="secondary" onClick={() => setShowAddForm(false)}>
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit Book Modal */}
      {showEditForm && editingBook && (
        <div className="modal-overlay" onClick={() => setShowEditForm(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>Edit Book</h3>
            <form onSubmit={handleSaveEdit}>
              <div>
                <label>Title</label>
                <input
                  type="text"
                  value={editFormData.title}
                  onChange={(e) => setEditFormData({ ...editFormData, title: e.target.value })}
                  placeholder="Book title"
                  required
                />
              </div>
              <div>
                <label>Author</label>
                <input
                  type="text"
                  value={editFormData.author}
                  onChange={(e) => setEditFormData({ ...editFormData, author: e.target.value })}
                  placeholder="Author name"
                  required
                />
              </div>
              <div>
                <label>Subject</label>
                <select
                  value={editFormData.subject}
                  onChange={(e) => setEditFormData({ ...editFormData, subject: e.target.value })}
                  required
                >
                  <option value="">Select subject</option>
                  {subjects.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </div>

              <div className="copy-management">
                <label>Available Copies</label>
                <input
                  type="number"
                  value={editFormData.available_copies}
                  onChange={(e) => setEditFormData({ ...editFormData, available_copies: e.target.value })}
                  min="0"
                  required
                />
              </div>

              <div className="copy-management">
                <label>Total Copies</label>
                <input
                  type="number"
                  value={editFormData.total_copies}
                  onChange={(e) => setEditFormData({ ...editFormData, total_copies: e.target.value })}
                  min="0"
                  required
                />
                <p className="copy-info" style={{ marginTop: "0.5rem", fontSize: "0.85rem" }}>
                  Borrowed: <strong>{editingBook.borrowed_copies}</strong>
                </p>
              </div>

              <div style={{ display: "flex", gap: ".75rem", marginTop: "1rem" }}>
                <button type="submit" className="primary" disabled={submitting}>
                  {submitting ? "Saving..." : "Save Changes"}
                </button>
                <button type="button" className="secondary" onClick={() => setShowEditForm(false)}>
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {message && <p className="notice">{message}</p>}

      {loading ? (
        <div className="loading-state">
          <p className="notice">⏳ Loading books...</p>
        </div>
      ) : books.length === 0 ? (
        <div className="empty-state">
          <p className="empty">📚 No books found</p>
          <p style={{ fontSize: ".9rem", color: "var(--muted)" }}>
            {subject ? "Try selecting a different subject." : "Start by adding some books!"}
          </p>
        </div>
      ) : viewMode === "cards" ? (
        <div className="books-cards-grid">
          {books.map((book) => (
            <div key={book.id} className="book-card">
              <div className="book-card-header">
                <h3>{book.title}</h3>
                {book.available_copies <= 0 && <span className="badge unavailable">Out of Stock</span>}
              </div>
              <div className="book-card-body">
                <p className="book-author">by <strong>{book.author}</strong></p>
                <p className="book-subject">
                  <span className="subject-tag">{book.subject}</span>
                </p>
                <div className="book-copies">
                  <div className="copies-info">
                    <span className="copies-label">Available:</span>
                    <span className={`copies-count ${book.available_copies > 0 ? "available" : "unavailable"}`}>
                      {book.available_copies} / {book.total_copies}
                    </span>
                  </div>
                  <div className="progress-bar">
                    <div
                      className="progress-fill"
                      style={{
                        width: `${(book.available_copies / book.total_copies) * 100}%`,
                      }}
                    ></div>
                  </div>
                </div>
              </div>
              <div className="book-card-footer">
                {canBorrow && (
                  <button
                    className={`btn-action primary ${book.available_copies <= 0 ? "disabled" : ""}`}
                    disabled={book.available_copies <= 0}
                    onClick={() => borrowBook(book)}
                  >
                    📖 Borrow
                  </button>
                )}
                
                {user && user.role === "admin" && (
                  <>
                    <button
                      className="btn-action secondary"
                      onClick={() => handleEditBook(book)}
                    >
                      ✏️ Edit
                    </button>
                    <button
                      className="btn-action success"
                      onClick={() => handleAddCopy(book)}
                    >
                      ➕ Add
                    </button>
                    <button
                      className="btn-action warning"
                      onClick={() => handleRemoveCopy(book)}
                    >
                      ➖ Remove
                    </button>
                    <button
                      className="btn-action danger"
                      onClick={() => handleDeleteBook(book.id, book.title)}
                    >
                      🗑️ Delete
                    </button>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="books-table-container">
          <table className="books-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Author</th>
                <th>Subject</th>
                <th className="copies-col">Available</th>
                {canBorrow && <th>Action</th>}
                {user?.role === "admin" && <th>Manage</th>}
              </tr>
            </thead>
            <tbody>
              {books.map((book) => (
                <tr key={book.id} className={`book-row ${book.available_copies <= 0 ? "unavailable-row" : ""}`}>
                  <td className="title-cell"><strong>{book.title}</strong></td>
                  <td>{book.author}</td>
                  <td><span className="subject-tag-table">{book.subject}</span></td>
                  <td className="copies-col">
                    <span className={`copies-badge ${book.available_copies > 0 ? "available" : "unavailable"}`}>
                      {book.available_copies}/{book.total_copies}
                    </span>
                  </td>
                  {canBorrow && (
                    <td>
                      <button
                        className="primary"
                        disabled={book.available_copies <= 0}
                        onClick={() => borrowBook(book)}
                      >
                        {book.available_copies > 0 ? "Borrow" : "Unavailable"}
                      </button>
                    </td>
                  )}
                  {user?.role === "admin" && (
                    <td>
                      <div className="action-buttons-compact">
                        <button
                          className="btn-table-edit"
                          onClick={() => handleEditBook(book)}
                          title="Edit"
                        >
                          ✏️
                        </button>
                        <button
                          className="btn-table-add"
                          onClick={() => handleAddCopy(book)}
                          title="Add 1 copy"
                        >
                          ➕
                        </button>
                        <button
                          className="btn-table-remove"
                          onClick={() => handleRemoveCopy(book)}
                          title="Remove 1 copy"
                        >
                          ➖
                        </button>
                        <button
                          className="btn-table-delete"
                          onClick={() => handleDeleteBook(book.id, book.title)}
                          title="Delete"
                        >
                          🗑️
                        </button>
                      </div>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
