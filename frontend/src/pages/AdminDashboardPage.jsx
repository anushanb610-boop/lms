import { useEffect, useState } from "react";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend,
  ArcElement,
} from 'chart.js';
import { Bar, Pie } from 'react-chartjs-2';
import { api } from "../api";
import { PageHeader } from "../components/PageHeader";
import { formatDateShort } from "../utils/date";
import { onRefreshNeeded } from "../hooks/useRefresh";

ChartJS.register(CategoryScale, LinearScale, BarElement, ArcElement, Title, Tooltip, Legend);

export default function AdminDashboardPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  const fetchData = () => {
    api.adminDashboard().then(setData).catch((e) => setError(e.message));
  };

  useEffect(() => {
    fetchData();
  }, []);

  useEffect(() => {
    // Register for refresh signals
    const unsubscribe = onRefreshNeeded(fetchData);
    return () => unsubscribe();
  }, []);

  if (error) {
    return (
      <div className="card page-card">
        <PageHeader title="Dashboard" />
        <p className="error">{error}</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="card page-card">
        <PageHeader title="Dashboard" />
        <p className="notice">Loading dashboard data...</p>
      </div>
    );
  }

  const labels = (data.activity || []).map((a) => a.date);
  const counts = (data.activity || []).map((a) => a.count);
  const chartData = {
    labels,
    datasets: [
      {
        label: 'Borrows',
        data: counts,
        backgroundColor: 'rgba(67,56,202,0.8)',
        borderRadius: 10,
      },
    ],
  };
  const chartOptions = {
    responsive: true,
    maintainAspectRatio: true,
    plugins: {
      legend: { display: false },
      tooltip: { enabled: true },
      title: { display: false },
    },
    scales: {
      x: { grid: { display: false }, ticks: { font: { size: 11 } } },
      y: { beginAtZero: true, ticks: { font: { size: 11 } } },
    },
  };

  // Borrower statistics charts
  const borrowerLabels = (data.borrower_stats || []).map((b) => b.name);
  const borrowerCounts = (data.borrower_stats || []).map((b) => b.count);
  
  const borrowerBarChartData = {
    labels: borrowerLabels,
    datasets: [
      {
        label: 'Books Borrowed',
        data: borrowerCounts,
        backgroundColor: [
          'rgba(67,56,202,0.8)',
          'rgba(99,102,241,0.8)',
          'rgba(139,92,246,0.8)',
          'rgba(168,85,247,0.8)',
          'rgba(190,24,93,0.8)',
        ],
        borderRadius: 10,
      },
    ],
  };

  const borrowerBarChartOptions = {
    indexAxis: 'y',
    responsive: true,
    maintainAspectRatio: true,
    plugins: {
      legend: { display: false },
      tooltip: { enabled: true },
      title: { display: false },
    },
    scales: {
      x: { beginAtZero: true, ticks: { font: { size: 11 } } },
      y: { ticks: { font: { size: 11 } } },
    },
  };

  const colors = [
    'rgba(67,56,202,0.8)',
    'rgba(99,102,241,0.8)',
    'rgba(139,92,246,0.8)',
    'rgba(168,85,247,0.8)',
    'rgba(190,24,93,0.8)',
    'rgba(244,63,94,0.8)',
    'rgba(249,115,22,0.8)',
    'rgba(251,146,60,0.8)',
    'rgba(34,197,94,0.8)',
    'rgba(59,130,246,0.8)',
  ];

  const borrowerPieChartData = {
    labels: borrowerLabels,
    datasets: [
      {
        label: 'Books Borrowed',
        data: borrowerCounts,
        backgroundColor: colors.slice(0, borrowerLabels.length),
        borderWidth: 2,
        borderColor: '#fff',
      },
    ],
  };

  const borrowerPieChartOptions = {
    responsive: true,
    maintainAspectRatio: true,
    plugins: {
      legend: {
        display: true,
        position: 'bottom',
        labels: { font: { size: 11 }, padding: 15 },
      },
      tooltip: { enabled: true },
      title: { display: false },
    },
  };

  return (
    <div className="page-card admin-page-card">
      <PageHeader
        title="Admin Dashboard"
      />

      <div className="dashboard-grid">
        <div className="stat-card">
          <span className="stat-label">Total Books</span>
          <strong>{data.total_books}</strong>
        </div>
        <div className="stat-card">
          <span className="stat-label">Total Users</span>
          <strong>{data.total_users}</strong>
        </div>
        <div className="stat-card">
          <span className="stat-label">Currently Borrowed</span>
          <strong>{data.borrowed}</strong>
        </div>
        <div className="stat-card overdue-card">
          <span className="stat-label">Overdue Books</span>
          <strong>{data.overdue}</strong>
        </div>
      </div>

      <section className="dashboard-sections">
        <div className="dashboard-panel">
          <div className="section-card">
            <div className="section-card-header">
              <h3>Upcoming Due Dates</h3>
              <span className="section-note">Next 7 days</span>
            </div>
            {data.upcoming.length === 0 ? (
              <p className="empty">No upcoming due dates.</p>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>Due Date</th>
                    <th>Book</th>
                    <th>User</th>
                  </tr>
                </thead>
                <tbody>
                  {data.upcoming.map((r) => (
                    <tr key={r.id}>
                      <td>{formatDateShort(r.due_date)}</td>
                      <td>{r.title}</td>
                      <td>{r.borrower_name}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        <div className="dashboard-panel">
          <div className="section-card chart-card">
            <div className="section-card-header">
              <h3>Borrower Statistics</h3>
              <span className="section-note">Books borrowed by borrower</span>
            </div>
            {(data.borrower_stats || []).length === 0 ? (
              <p className="empty">No borrower data.</p>
            ) : (
              <div className="chart-container">
                <Bar data={borrowerBarChartData} options={borrowerBarChartOptions} />
              </div>
            )}
          </div>
        </div>

        <div className="dashboard-panel">
          <div className="section-card chart-card">
            <div className="section-card-header">
              <h3>Borrower Distribution</h3>
              <span className="section-note">Pie chart view</span>
            </div>
            {(data.borrower_stats || []).length === 0 ? (
              <p className="empty">No borrower data.</p>
            ) : (
              <div className="chart-container">
                <Pie data={borrowerPieChartData} options={borrowerPieChartOptions} />
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
