// analytics.js – 優化版（摺疊 + 載入更多）

let currentCamera = "";
let hourlyChart = null;
let weeklyChart = null;
let customChart = null;

// 載入更多相關變數
let allSafetyRecords = [];

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

// === 折線圖:近 24 小時 ===
function loadHourlyChart() {
  fetch(`/api/people/hourly?camera_id=${currentCamera}`)
    .then(res => res.json())
    .then(data => {
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
              callbacks: { label: ctx => `People Count:${ctx.parsed.y}` }
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

// === 柱狀圖:近 7 天 ===
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
              callbacks: { label: ctx => `People Count:${ctx.parsed.y}` }
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

// === 自訂時段:純柱狀圖 ===
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
                callbacks: { label: ctx => `People Count:${ctx.parsed.y}` }
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

  loadCustomData("09:00", "18:00");

  document.getElementById("filterBtn").addEventListener("click", () => {
    const start = document.getElementById("startTime").value;
    const end = document.getElementById("endTime").value;
    loadCustomData(start, end);
  });
}

// ========================================
// AI Safety Records (優化版 - 載入更多)
// ========================================

async function loadSafetyRecords() {
  const cam = document.getElementById("safetyCameraSelect").value;
  const res = await fetch(`/api/safety/list?camera_id=${cam}`);
  const data = await res.json();

  const box = document.getElementById("safetyList");
  box.innerHTML = "";

  if (data.length === 0) {
    box.innerHTML = `
      <div style="text-align:center; padding:40px; color:#6b7280;">
        <p style="font-size:18px;">📋 尚無安全分析記錄</p>
        <p style="font-size:14px; margin-top:8px;">等待系統自動執行分析...</p>
      </div>
    `;
    return;
  }

  // 直接一次 append 全部
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
        <small style="opacity:0.6">${formatDateTime(r.created_at)}</small>
      </div>

      <button class="safety-btn">▼ 詳細</button>
    `;

    div.querySelector(".safety-btn").onclick = () => openSafetyPanel(r, div);
    box.appendChild(div);
  });
}

// ========================================
// 展開完整分析 (優化版 - 可摺疊)
// ========================================

function openSafetyPanel(data, parentDiv) {
  // 若已展開 → 收合
  const next = parentDiv.nextElementSibling;
  if (next && next.classList.contains("safety-expand")) {
    next.remove();
    parentDiv.querySelector(".safety-btn").textContent = "▼ 詳細";
    return;
  }

  // 收起其他展開內容
  document.querySelectorAll(".safety-expand").forEach(el => el.remove());
  document.querySelectorAll(".safety-btn").forEach(btn => btn.textContent = "▼ 詳細");

  // 更改按鈕文字
  parentDiv.querySelector(".safety-btn").textContent = "▲ 收合";

  // === 安全處理 Issues ===
  let issues = parseJSON(data.issues, []);

  // === 安全處理 Suggestions ===
  let suggestions = parseJSON(data.suggestions, []);

  // === 安全處理 Legal Refs ===
  let legalRefs = parseJSON(data.legal_refs, []);

  // === 圖片來源:優先使用 base64 ===
  let imageSrc = "";
  if (data.image_base64 && data.image_base64.trim() !== "") {
    imageSrc = `data:image/jpeg;base64,${data.image_base64}`;
  } else if (data.image_url) {
    imageSrc = data.image_url;
  }

  // === 取得 merged_compliance_detail ===
  let complianceDetail = data.merged_compliance_detail || "";
  
  if (!complianceDetail && legalRefs.length > 0) {
    complianceDetail = legalRefs
      .map(law => law.content_summary || "")
      .filter(text => text.trim() !== "")
      .join(" ");
  }

  // === Create expand div ===
  const expand = document.createElement("div");
  expand.className = "safety-expand";

  expand.innerHTML = `
    <div class="expand-layout">
      
      <!-- 圖片 -->
      ${imageSrc ? `<img src="${imageSrc}" class="expand-img" alt="Safety Image">` : '<p style="color:#999;">無圖片</p>'}

      <!-- 內容區 -->
      <div class="expand-right">
        
        <!-- ⚠️ 檢測問題 (可摺疊) -->
        ${issues.length > 0 ? `
          <div class="collapsible-section">
            <div class="collapsible-header issue" onclick="toggleCollapse(this)">
              <div class="collapsible-title">
                <span class="icon-title icon-issue">⚠</span>
                <span>檢測問題 (${issues.length})</span>
              </div>
              <span class="collapsible-toggle">▼</span>
            </div>

            <div class="collapsible-content">
              <div class="collapsible-content-inner issue">
                <ul style="list-style: none; padding: 0; margin: 0;">
                  ${issues.map((issue, idx) => {
                    const severityBadge = `<span class="severity-badge ${issue.severity || 'medium'}">${getSeverityText(issue.severity)}</span>`;
                    return `
                      <li class="issue-item">
                        <div class="issue-header">
                          <strong>${issue.name || "未命名問題"}</strong>
                          ${severityBadge}
                        </div>
                        <p class="issue-desc">
                          ${issue.description || ""}
                        </p>
                      </li>
                    `;
                  }).join("")}
                </ul>
              </div>
            </div>
          </div>
        ` : '<p style="color:#16a34a; font-weight:600; margin-bottom: 15px;">✅ 未發現明顯問題</p>'}

        <!-- ✨ 改善建議 (可摺疊) -->
        ${suggestions.length > 0 ? `
          <div class="collapsible-section">
            <div class="collapsible-header suggestions" onclick="toggleCollapse(this)">
              <div class="collapsible-title">
                <span class="icon-title icon-sug">✨</span>
                <span>改善建議 (${suggestions.length})</span>
              </div>
              <span class="collapsible-toggle">▼</span>
            </div>
            <div class="collapsible-content">
              <div class="collapsible-content-inner suggestions">
                <ul class="suggestion-list">
                  ${suggestions.map(sug => `
                    <li>${sug}</li>
                  `).join("")}
                </ul>
              </div>
            </div>
          </div>
        ` : ""}

      </div>
      
    </div>

    <!-- 法規依據 (不可摺疊) -->
    ${legalRefs.length > 0 ? `
      <div class="legal-fullwidth">
        <div class="law-header">
          <div class="law-header-title">
            <span class="icon-title icon-law">📚</span>
            <span>法規依據</span>
          </div>
        </div>

        <div class="legal-fw-box">

          <!-- 📘 適用法規 -->
          <div class="law-block">
            <div class="law-block-title">■ 適用法規：</div>
            <ul class="law-list">
              ${legalRefs.map(law => {
                const lawName = law.law_name || law.law || "未知法規";
                const article = law.article || "";
                const content = law.full_content || law.content_summary || law.content || "";
                
                return `
                <li>
                  <span class="law-one-line">
                    • ${lawName}${article} - ${content}
                  </span>
                </li>
                `;
              }).join("")}
            </ul>
          </div>

          <!-- 📙 合規詳情 -->
          ${complianceDetail ? `
            <div class="law-block">
              <div class="law-block-title">■ 合規詳情：</div>
              <p class="law-detail">
                ${complianceDetail}
              </p>
            </div>
          ` : ""}

        </div>
      </div>
    ` : ""}

    <p class="created-time">📅 分析時間: ${formatDateTime(data.created_at)}</p>
  `;

  parentDiv.after(expand);

  // // 展開後自動滾動
  // setTimeout(() => {
  //   expand.scrollIntoView({ behavior: "smooth", block: "start" });
  // }, 100);
}

// ========================================
// 摺疊/展開功能
// ========================================

function toggleCollapse(header) {
  const content = header.nextElementSibling;
  const toggle = header.querySelector(".collapsible-toggle");

  // 先把同一個 expand-right 裡其他展開的收起來
  const parent = header.closest(".expand-right");
  const allContents = parent.querySelectorAll(".collapsible-content.expanded");

  allContents.forEach(c => {
    if (c !== content) {
      c.classList.remove("expanded");
      const hdr = c.previousElementSibling;
      hdr.querySelector(".collapsible-toggle").classList.remove("expanded");
    }
  });

  // 自己切換
  if (content.classList.contains("expanded")) {
    content.classList.remove("expanded");
    toggle.classList.remove("expanded");
  } else {
    content.classList.add("expanded");
    toggle.classList.add("expanded");
  }
}


// ========================================
// 工具函數
// ========================================

function parseJSON(data, defaultValue) {
  if (Array.isArray(data)) return data;
  if (typeof data === "object" && data !== null) return data;
  if (typeof data === "string") {
    const s = data.trim();
    if (s === "" || s === "null" || s === "None") return defaultValue;
    try {
      const parsed = JSON.parse(s);
      return parsed || defaultValue;
    } catch {
      return defaultValue;
    }
  }
  return defaultValue;
}

function getSafetyLevelByScore(score) {
  if (score >= 80) return "excellent";
  if (score >= 60) return "good";
  if (score >= 40) return "fair";
  return "poor";
}

function getSeverityText(severity) {
  const map = {
    "high": "高風險",
    "medium": "中風險",
    "low": "低風險"
  };
  return map[severity] || "未知";
}

function formatDateTime(dateStr) {
  if (!dateStr) return "未知時間";
  const d = new Date(dateStr);
  return `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`;
}

function formatDate(dateStr) {
  const d = new Date(dateStr);
  return `${d.getMonth() + 1}/${d.getDate()}`;
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