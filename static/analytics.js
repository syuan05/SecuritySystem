let currentCamera = "";
let hourlyChart = null;
let weeklyChart = null;
let customChart = null;

document.addEventListener("DOMContentLoaded", () => {
  loadCameraOptions().then(() => {
    renderAllCharts();
  });

  document.getElementById("cameraSelect").addEventListener("change", e => {
    currentCamera = e.target.value;
    renderAllCharts();
  });
});

// === 載入攝影機清單 ===
async function loadCameraOptions() {
  const res = await fetch("/api/cameras");
  const data = await res.json();
  const select = document.getElementById("cameraSelect");

  data.forEach(cam => {
    const opt = document.createElement("option");
    opt.value = cam.camera_id;
    opt.textContent = cam.camera_name;
    select.appendChild(opt);
  });
}

function renderAllCharts() {
  loadHourlyChart();
  loadWeeklyChart();
  setupCustomChart();
}

// === 折線圖：近 24 小時 ===
function loadHourlyChart() {
  fetch(`/api/people/hourly?camera_id=${currentCamera}`)
    .then(res => res.json())
    .then(data => {
      // 先建立 24 小時的完整列表
      const fullHours = Array.from({ length: 24 }, (_, i) => i);
      const hourMap = Object.fromEntries(data.map(d => [d.hour, d.count]));
      const labels = fullHours.map(h => `${h}:00`);
      const values = fullHours.map(h => hourMap[h] || 0);

      if (hourlyChart) hourlyChart.destroy();

      const ctx = document.getElementById("hourlyChart");
      hourlyChart = new Chart(ctx, {
        type: "line",
        data: {
          labels,
          datasets: [{
            label: "People (Last 24h)",
            data: values,
            borderColor: "#36A2EB",
            backgroundColor: "rgba(54,162,235,0.25)",
            fill: true,
            tension: 0.35,
            pointRadius: 4,
            pointBackgroundColor: "#36A2EB"
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              backgroundColor: "rgba(15,23,42,0.9)",
              titleFont: { size: 14, weight: "bold" },
              bodyFont: { size: 13 },
              padding: 10,
              cornerRadius: 8,
              callbacks: { label: ctx => `人數：${ctx.parsed.y}` }
            }
          },
          scales: {
            x: {
              title: { display: true, text: "Hour of Day" },
              ticks: { maxTicksLimit: 12 }
            },
            y: {
              beginAtZero: true,
              title: { display: true, text: "People Count" }
            }
          }
        }
      });
    });
}

// === 柱狀圖：近 7 天 ===
function loadWeeklyChart() {
  fetch(`/api/people/weekly?camera_id=${currentCamera}`)
    .then(res => res.json())
    .then(data => {
      const labels = data.map(d => formatDate(d.date));
      const values = data.map(d => d.count);

      if (weeklyChart) weeklyChart.destroy();

      const ctx = document.getElementById("weeklyChart");
      weeklyChart = new Chart(ctx, {
        type: "bar",
        data: {
          labels,
          datasets: [{
            label: "People (Last 7 days)",
            data: values,
            backgroundColor: "rgba(75,192,192,0.6)",
            borderRadius: 6
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              backgroundColor: "rgba(15,23,42,0.9)",
              callbacks: { label: ctx => `人數：${ctx.parsed.y}` }
            }
          },
          scales: {
            x: {
              title: { display: true, text: "Date" },
              ticks: { autoSkip: false, maxRotation: 0, minRotation: 0 }
            },
            y: {
              beginAtZero: true,
              title: { display: true, text: "People Count" }
            }
          }
        }
      });
    });
}

// === 自訂時段：純柱狀圖 ===
function setupCustomChart() {
  const ctx = document.getElementById("customChart");
  if (customChart) customChart.destroy();

  function loadCustomData(start, end) {
    fetch(`/api/people/custom?start=${start}&end=${end}&camera_id=${currentCamera}`)
      .then(res => res.json())
      .then(data => {
        const labels = data.map(d => formatDate(d.date));
        const values = data.map(d => d.count);

        if (customChart) customChart.destroy();

        customChart = new Chart(ctx, {
          type: "bar",
          data: {
            labels,
            datasets: [{
              label: "People Count",
              data: values,
              backgroundColor: "rgba(255,99,132,0.6)",
              borderRadius: 6
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { display: false },
              tooltip: {
                backgroundColor: "rgba(15,23,42,0.9)",
                callbacks: { label: ctx => `人數：${ctx.parsed.y}` }
              }
            },
            scales: {
              x: {
                title: { display: true, text: "Date" },
                ticks: { autoSkip: false, maxRotation: 0, minRotation: 0 }
              },
              y: {
                beginAtZero: true,
                title: { display: true, text: "People Count" }
              }
            }
          }
        });
      });
  }

  // 初始
  loadCustomData("09:00", "18:00");

  document.getElementById("filterBtn").addEventListener("click", () => {
    const start = document.getElementById("startTime").value;
    const end = document.getElementById("endTime").value;
    loadCustomData(start, end);
  });
}

// === 日期格式工具 ===
function formatDate(dateStr) {
  const d = new Date(dateStr);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}
