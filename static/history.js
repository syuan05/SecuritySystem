function formatDateTime(dateStr) {
  // 轉成 yyyy-mm-dd HH:MM:ss (英文格式)
  const date = new Date(dateStr);
  if (isNaN(date)) return dateStr;
  const pad = n => n.toString().padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} `
       + `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

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
    const data = await res.json();

    const tbody = document.querySelector("#eventTable tbody");
    tbody.innerHTML = "";

    if (data.length === 0) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td colspan="6" class="no-data">No records found</td>`;
      tbody.appendChild(tr);
      return;
    }

    for (const e of data) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${e.event_id}</td>
        <td>${e.camera_name || "—"}</td>
        <td>${e.gate_name || "—"}</td>
        <td>${e.event_type}</td>
        <td class="${e.alert_level}">${e.alert_level}</td>
        <td>${formatDateTime(e.timestamp)}</td>
      `;
      tbody.appendChild(tr);
    }
  } catch (err) {
    console.error(err);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("filterBtn").addEventListener("click", loadEvents);
  loadEvents();
});
