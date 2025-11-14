function formatDateTime(dateStr) {
  // 轉成 yyyy-mm-dd HH:MM:ss (英文格式)
  const date = new Date(dateStr);
  if (isNaN(date)) return dateStr;
  const pad = n => n.toString().padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} `
    + `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

function getEventIcon(type) {
  switch (type) {

    case "inout":
      return "↔️"; // One-way / Gate crossing

    case "intrusion":
      return "🚨";

    case "climbing":
      return "🧗";

    case "falling":
      return "🤸‍♂️"; // 或你要換成 ❗️ 也可以

    default:
      return "•";
  }
}

function formatEventName(type) {
  const map = {
    inout: "One-way",
    intrusion: "Intrusion",
    climbing: "Climbing",
    falling: "Falling",
  };

  return map[type] || type;
}

let fullData = [];
let currentPage = 1;

function renderTable() {
  const tbody = document.querySelector("#eventTable tbody");
  tbody.innerHTML = "";

  const rowsPerPage = parseInt(document.getElementById("rowsPerPage").value);
  const start = (currentPage - 1) * rowsPerPage;
  const end = start + rowsPerPage;

  const pageData = fullData.slice(start, end);

  if (pageData.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" class="no-data">No records</td></tr>`;
    return;
  }

  for (const e of pageData) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${e.event_id}</td>
      <td>${e.camera_name || "—"}</td>
      <td>${e.gate_name || "—"}</td>

      <td class="event-type">
        <span class="icon">${getEventIcon(e.event_type)}</span>
        ${formatEventName(e.event_type)}
      </td>

      <td><span class="level-tag level-${e.alert_level}">${e.alert_level}</span></td>

      <td>${formatDateTime(e.timestamp)}</td>
    `;
    tbody.appendChild(tr);
  }

  document.getElementById("pageInfo").innerText =
    `Page ${currentPage} / ${Math.ceil(fullData.length / rowsPerPage)}`;
}

// 分頁按鈕
document.getElementById("prevPage").onclick = () => {
  if (currentPage > 1) { currentPage--; renderTable(); }
};
document.getElementById("nextPage").onclick = () => {
  const rowsPerPage = parseInt(document.getElementById("rowsPerPage").value);
  if (currentPage < Math.ceil(fullData.length / rowsPerPage)) {
    currentPage++; renderTable();
  }
};

// rows per page change
document.getElementById("rowsPerPage").onchange = () => {
  currentPage = 1;
  renderTable();
};
async function loadEvents() {
  const start = document.getElementById("startDate").value;
  const end = document.getElementById("endDate").value;
  const type = document.getElementById("typeSelect").value;
  const level = document.getElementById("levelSelect").value;

  const params = new URLSearchParams();
  if (start) params.append("start", start + " 00:00:00");
  if (end) params.append("end", end + " 23:59:59");
  if (type) params.append("type", type);
  if (level) params.append("level", level);

  try {
    const res = await fetch("/api/events?" + params.toString());
    if (!res.ok) throw new Error("Failed to fetch events");

    fullData = await res.json();  // ⬅ 更新資料給分頁用
    currentPage = 1;              // ⬅ 回到第 1 頁
    renderTable();                // ⬅ 用分頁渲染畫面

  } catch (err) {
    console.error(err);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("filterBtn").addEventListener("click", loadEvents);
  loadEvents();
});

