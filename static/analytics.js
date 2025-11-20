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

// ======== Tab 切換 ========
document.addEventListener("DOMContentLoaded", () => {

  const tabFlow = document.getElementById("tab-flow");
  const tabSafety = document.getElementById("tab-safety");
  const flowSection = document.getElementById("flow-section");
  const safetySection = document.getElementById("safety-section");

  tabFlow.onclick = () => {
    tabFlow.classList.add("active");
    tabSafety.classList.remove("active");
    flowSection.classList.remove("hidden");
    safetySection.classList.add("hidden");
  };

  tabSafety.onclick = () => {
    tabSafety.classList.add("active");
    tabFlow.classList.remove("active");
    safetySection.classList.remove("hidden");
    flowSection.classList.add("hidden");
    loadSafetyRecords();
  };
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
      // convert timestamp list → hour buckets
      let now = new Date();
      let buckets = [];

      for (let i = 23; i >= 0; i--) {
        let t = new Date(now.getTime() - i * 3600 * 1000);
        let hour = t.getHours();
        buckets.push({
          label: `${hour}:00`,
          start: t,
          end: new Date(t.getTime() + 3600 * 1000),
          count: 0
        });
      }

      // count events into correct bucket
      data.forEach(row => {
        let ts = new Date(row.timestamp);
        buckets.forEach(b => {
          if (ts >= b.start && ts < b.end) {
            b.count++;
          }
        });
      });

      const labels = buckets.map(b => b.label);
      const values = buckets.map(b => b.count);
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
              callbacks: { label: ctx => `People Count：${ctx.parsed.y}` }
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
              callbacks: { label: ctx => `People Count：${ctx.parsed.y}` }
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
                callbacks: { label: ctx => `People Count：${ctx.parsed.y}` }
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

async function loadSafetyRecords() {
  const cam = document.getElementById("safetyCameraSelect").value;
  const res = await fetch(`/api/safety/list?camera_id=${cam}`);
  const data = await res.json();

  const box = document.getElementById("safetyList");
  box.innerHTML = "";

  data.forEach(r => {
    const level = getSafetyLevelByScore(r.safety_score);
    const div = document.createElement("div");
    div.className = "safety-item";

    div.innerHTML = `
  <div class="safety-score ${level}">
    ${r.safety_score ?? "--"}
  </div>

  <div style="flex:1; padding:0 15px;">
    <b>${r.camera_name}</b> (${r.location_type || "Unknown"})<br>
    <small>${r.summary || ""}</small><br>
    <small style="opacity:0.6">${r.created_at}</small>
  </div>

  <button class="safety-btn">▼</button>
`;

    div.querySelector(".safety-btn").onclick = () => openSafetyPanel(r, div);

    box.appendChild(div);
  });
}
function openSafetyPanel(data, parentDiv) {
  // 若已展開 → 收合
  const next = parentDiv.nextElementSibling;
  if (next && next.classList.contains("safety-expand")) {
    next.remove();
    return;
  }

  // 收起其他展開內容
  document.querySelectorAll(".safety-expand").forEach(el => el.remove());

  // === 安全處理 Issues ===
  let issues = [];
  if (Array.isArray(data.issues)) {
    issues = data.issues;
  } else if (typeof data.issues === "string") {
    const s = data.issues.trim();
    if (s !== "" && s !== "null" && s !== "None") {
      try {
        const parsed = JSON.parse(s);
        if (Array.isArray(parsed)) issues = parsed;
      } catch { }
    }
  }

  // === 安全處理 Suggestions ===
  let suggestions = [];
  if (Array.isArray(data.suggestions)) {
    suggestions = data.suggestions;
  } else if (typeof data.suggestions === "string") {
    const s = data.suggestions.trim();
    if (s !== "" && s !== "null" && s !== "None") {
      try {
        const parsed = JSON.parse(s);
        if (Array.isArray(parsed)) suggestions = parsed;
        else suggestions = [s];
      } catch {
        suggestions = [s];
      }
    }
  }

  // === Create expand div ===
  const expand = document.createElement("div");
  expand.className = "safety-expand";

  expand.innerHTML = `
    <div class="expand-layout">
      
      <div class="expand-left">
        <img src="${data.image_url || ""}" class="expand-img">
      </div>

      <div class="expand-right">

        <h4><span class="icon-title icon-issue">⚠</span> Safety Issues</h4>
        <ul>
          ${issues.map(i => `
            <li>
              <b>${i.name}</b> — ${i.description}
              ${i.law ? `<span style="color:#888;">（${i.law}）</span>` : ""}
            </li>
          `).join("")}
        </ul>

        <h4><span class="icon-title icon-sug">✨</span> Suggestions</h4>
        <ul>
          ${suggestions.map(s => `<li>${s}</li>`).join("")}
        </ul>

        <p class="created-time">Created: ${data.created_at}</p>
      </div>

    </div>
  `;


  parentDiv.after(expand);

  // ⭐ 展開後自動滾動
  setTimeout(() => {
    expand.scrollIntoView({ behavior: "smooth", block: "start" });
  }, 80);
}


function getSafetyLevelByScore(score) {
  if (score >= 80) return "excellent";
  if (score >= 60) return "good";
  if (score >= 40) return "fair";
  return "poor";
}

// 攝影機下拉清單
document.addEventListener("DOMContentLoaded", async () => {
  const res = await fetch("/api/cameras");
  const cams = await res.json();

  const sel = document.getElementById("safetyCameraSelect");
  cams.forEach(c => {
    const opt = document.createElement("option");
    opt.value = c.camera_id;
    opt.textContent = c.camera_name;
    sel.appendChild(opt);
  });

  sel.onchange = loadSafetyRecords;
});

// === 日期格式工具 ===
function formatDate(dateStr) {
  const d = new Date(dateStr);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}
