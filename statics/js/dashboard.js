// static/js/dashboard.js
document.addEventListener("DOMContentLoaded", () => {
  console.log("Dashboard JS loaded...");
  loadDashboardData();
  setInterval(loadDashboardData, 60000); // Refresh every 60 seconds
});

let previousData = {};

function loadDashboardData() {
  fetch("/api/dashboard_data")
    .then(response => response.json())
    .then(data => {
      updateDashboard(data);
      previousData = data;
    })
    .catch(err => console.error("Failed to load dashboard data:", err));
}

function updateDashboard(data) {
  updateMetric("totalUsers", data.total_users);
  updateMetric("activeSubs", data.active_subscriptions);
  updateMetric("totalRevenue", "KSh " + data.total_revenue);
  updateMetric("unpaidInvoices", data.unpaid_invoices);

  renderRevenueChart(data.revenue_chart);
  renderPlanDistributionChart(data.plan_distribution);
}

// 🎯 Animate metric change with a brief color flash
function updateMetric(id, newValue) {
  const el = document.getElementById(id);
  if (!el) return;

  const oldValue = el.textContent;
  el.textContent = newValue;

  if (oldValue !== newValue) {
    el.classList.add("updated");
    setTimeout(() => el.classList.remove("updated"), 1000);
  }
}

// 📊 Revenue over time chart
let revenueChartInstance = null;
function renderRevenueChart(revenueData) {
  const ctx = document.getElementById("revenueChart").getContext("2d");

  if (revenueChartInstance) {
    revenueChartInstance.data.labels = revenueData.labels;
    revenueChartInstance.data.datasets[0].data = revenueData.values;
    revenueChartInstance.update();
    return;
  }

  revenueChartInstance = new Chart(ctx, {
    type: "line",
    data: {
      labels: revenueData.labels,
      datasets: [{
        label: "Revenue (KSh)",
        data: revenueData.values,
        borderColor: "#0d6efd",
        backgroundColor: "rgba(13, 110, 253, 0.2)",
        fill: true,
        tension: 0.4,
        pointRadius: 4
      }]
    },
    options: {
      responsive: true,
      animation: { duration: 800 },
      plugins: {
        legend: { display: true },
        tooltip: { mode: "index", intersect: false }
      },
      scales: {
        x: { grid: { display: false } },
        y: { beginAtZero: true }
      }
    }
  });
}

// 🟢 Plan distribution chart
let planChartInstance = null;
function renderPlanDistributionChart(planData) {
  const ctx = document.getElementById("planChart").getContext("2d");

  if (planChartInstance) {
    planChartInstance.data.labels = planData.labels;
    planChartInstance.data.datasets[0].data = planData.values;
    planChartInstance.update();
    return;
  }

  planChartInstance = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: planData.labels,
      datasets: [{
        data: planData.values,
        backgroundColor: ["#0d6efd", "#198754", "#ffc107", "#dc3545", "#6610f2"]
      }]
    },
    options: {
      responsive: true,
      plugins: {
        legend: { position: "bottom" }
      },
      animation: { duration: 1000 }
    }
  });
}

