let cameraId = null;
window.onload = async function () {
  const imgStream = document.getElementById("videoStream");
  const canvas = document.getElementById("drawCanvas");
  const ctx = canvas.getContext("2d");

  let editingFence = null; // 正在編輯哪個 fence
  let dragTarget = null;   // "A" or "B"
  let drawing = false;
  let points = [];
  let currentType = null;

  const params = new URLSearchParams(window.location.search);
  cameraId = params.get("id");
  function applyTimePicker() {
    flatpickr("input[type='time']", {
      enableTime: true,
      noCalendar: true,
      time_24hr: true,
      dateFormat: "H:i"
    });
  }

  /* === 載入相機資料 === */
  async function loadCamera() {
    const res = await fetch(`/api/camera/${cameraId}`);
    const data = await res.json();

    console.log("Loaded camera data:", data);

    if (data.error) {
      alert("Camera not found");
      return;
    }

    // 顯示影片
    document.getElementById("cameraTitle").textContent = data.camera_name;
    imgStream.src = `/video_feed/${cameraId}`;

    document.getElementById("cam-name").value = data.camera_name || "";
    document.getElementById("cam-location").value = data.location || "";
    document.getElementById("cameraTitle").textContent = data.name;
    // === 綁定開關 ===
    const climbSwitch = document.getElementById("climb-switch");
    const fallSwitch = document.getElementById("fall-switch");
    climbSwitch.addEventListener("change", () =>
      toggleMode("climbing", climbSwitch.checked)
    );
    fallSwitch.addEventListener("change", () =>
      toggleMode("falling", fallSwitch.checked)
    );

    climbSwitch.checked = Boolean(data.climbing_detection_mode);
    fallSwitch.checked = Boolean(data.falling_detection_mode);

    // === 顯示時間 ===
    const s = data.schedules || {}; // ← ⚠️ 你漏了這行

    // === Climbing ===
    // === Climbing ===
    const climbTime = document.getElementById("climb-time");
    const cs = s.climbing || { start: "00:00", end: "23:59" };
    climbTime.innerHTML = `
  <input type="text" id="climbing-start" class="time-input" value="${cs.start}" ${data.climbing_detection_mode ? "" : "disabled"}>
  ~
  <input type="text" id="climbing-end" class="time-input" value="${cs.end}" ${data.climbing_detection_mode ? "" : "disabled"}>
`;
    if (data.climbing_detection_mode) {
      document.getElementById("climbing-start").addEventListener("change", () => updateSchedule("climbing"));
      document.getElementById("climbing-end").addEventListener("change", () => updateSchedule("climbing"));
    }

    // === Falling ===
    const fallTime = document.getElementById("fall-time");
    const fs = s.falling || { start: "00:00", end: "23:59" };
    fallTime.innerHTML = `
  <input type="text" id="falling-start" class="time-input" value="${fs.start}" ${data.falling_detection_mode ? "" : "disabled"}>
  ~
  <input type="text" id="falling-end" class="time-input" value="${fs.end}" ${data.falling_detection_mode ? "" : "disabled"}>
`;

    if (data.falling_detection_mode) {
      document.getElementById("falling-start").addEventListener("change", () => updateSchedule("falling"));
      document.getElementById("falling-end").addEventListener("change", () => updateSchedule("falling"));
    }

  }
  await loadCamera();

  imgStream.onload = function () {
    canvas.width = imgStream.clientWidth;
    canvas.height = imgStream.clientHeight;
  };

  applyTimePicker();
  flatpickr(".time-input", {
    enableTime: true,
    noCalendar: true,
    dateFormat: "H:i",
    time_24hr: true,
    onChange: function (selectedDates, dateStr, instance) {
      const id = instance.element.id;
      const type = id.split("-")[0];
      updateSchedule(type);
    }
  });

  /* === 監聽所有 fence-btn === */
  document.querySelectorAll(".fence-btn").forEach(btn => {
    btn.addEventListener("click", async () => {
      const type = btn.dataset.type;
      currentType = type;
      const panel = document.getElementById(`${type}_panel`);

      // 🟡 先關掉所有其他的 fence panel
      document.querySelectorAll(".fence-panel").forEach(p => {
        if (p !== panel) p.classList.remove("active");
        p.classList.add("hidden");
      });

      // 🔵 切換目前這個
      const isOpen = panel.classList.contains("active");
      if (isOpen) {
        panel.classList.remove("active");
        panel.classList.add("hidden");
      } else {
        panel.classList.remove("hidden");
        panel.classList.add("active");

        // 🔹 若打開 -> 載入 fence 資料
        const res = await fetch(`/api/fence/${type}?camera_id=${cameraId}`);
        const data = await res.json();
        renderFenceList(data, type, panel);
      }
    });
  });

  /* === 畫線 === */


  /* === 渲染圍籬列表（已整合 Edit + Move）=== */
  function renderFenceList(fences, type, panel) {

    // 🧹 離開編輯或新增模式 → 清除拖曳相關設定
    canvas.onmousedown = null;
    canvas.onmousemove = null;
    canvas.onmouseup = null;
    points = [];
    drawing = false;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    panel.innerHTML = "";
    const list = document.createElement("div");

    if (fences.length === 0) {
      const msg = document.createElement("div");
      msg.textContent = "No fence added yet.";
      msg.style.color = "#666";
      msg.style.marginBottom = "8px";
      list.appendChild(msg);
    } else {
      fences.forEach(f => {
        const item = document.createElement("div");
        item.className = "fence-card";
        item.innerHTML = `
        <div class="fence-header">
          <span class="fence-name">${f.name}</span>
          <div class="fence-actions">
            <button class="fence-icon-btn edit-btn" data-id="${f.id}" title="Edit">
            ✎
            </button>
            <button class="fence-icon-btn delete-btn" data-id="${f.id}" title="Delete">
            🗑︎
            </button>
          </div>
        </div>
        <div class="fence-meta">
          <span>${f.direction}</span>
          ${currentType === "crowd"
            ? ""
            : `<span>${f.start_time} ~ ${f.end_time}</span>`
          }
        </div>
      `;
        list.appendChild(item);
      });
    }

    panel.appendChild(list);

    const addBtn = document.createElement("button");
    addBtn.textContent = "+ Add Fence";
    addBtn.className = "add-fence-btn";
    addBtn.onclick = startDrawing;
    panel.appendChild(addBtn);

    /* === 綁定 Edit / Delete === */
    panel.querySelectorAll(".edit-btn").forEach(btn => {
      btn.onclick = () => beginEditFence(btn.dataset.id, fences, panel);
    });

    panel.querySelectorAll(".delete-btn").forEach(btn => {
      btn.onclick = () => deleteFence(btn.dataset.id);
    });
  }

  async function deleteFence(id) {

    if (!confirm("Are you sure you want to delete this fence?")) return;

    await fetch(`/api/fence_delete/${id}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" }
    });

    // 更新 gate 線條（後端重載 config）
    await fetch(`/api/reload_gates/${cameraId}`, { method: "POST" });

    // 重新載入列表
    const panel = document.getElementById(`${currentType}_panel`);
    reloadFenceList(panel);

    console.log("Fence deleted:", id);
  }

  /* === 開始畫新圍籬 === */
  function startDrawing() {
    points = [];
    canvas.width = imgStream.clientWidth;
    canvas.height = imgStream.clientHeight;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    drawing = true;

    // 🧹 清掉 Edit 模式的拖曳監聽
    canvas.onmousedown = null;
    canvas.onmousemove = null;
    canvas.onmouseup = null
    console.log("開始框選:", currentType);
  }

  /* === 畫線（一般新增模式用）=== */
  canvas.addEventListener("click", (e) => {
    if (!drawing) return;

    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    points.push([x, y]);

    if (points.length === 2) {
      drawing = false;
      drawLine(points[0], points[1]);
      redrawFence();
      startAddDragMode();

      // 依照類型呼叫不同表單
      if (currentType === "crowd") {
        openCrowdFenceForm(points);   // People Counting 專用
      } else {
        openAddFenceForm(points);     // 一般 fence（含 Time）
      }
    }

  });
  function openAddFenceForm(points) {
    const panel = document.getElementById(`${currentType}_panel`);

    panel.innerHTML = `
    <div class="fence-form">
      <label>Fence Name</label>
      <input id="newFenceName" placeholder="Enter fence name">

      <label>Direction</label>
      <select id="newFenceDir">
        <option value="AtoB">A → B</option>
        <option value="BtoA">B → A</option>
      </select>

      <label>Time</label>
      <div style="display:flex; gap:6px;">
        <input id="newStart" type="time" value="09:00">
        <input id="newEnd" type="time" value="17:00">
      </div>

      <div class="btn-area">
        <button class="btn btn-primary" id="saveNewFenceBtn">Save</button>
        <button class="btn btn-secondary" id="cancelNewFenceBtn">Cancel</button>
      </div>
    </div>
  `;

    document.getElementById("saveNewFenceBtn").onclick =
      () => saveNewFence(points);
    applyTimePicker();

    document.getElementById("cancelNewFenceBtn").onclick =
      () => reloadFenceList(panel);
  }
  function startAddDragMode() {
    const videoW = imgStream.clientWidth;
    const videoH = imgStream.clientHeight;

    canvas.onmousedown = (e) => {
      const p = getCanvasXY(e);
      if (dist(p, points[0]) < 15) dragTarget = "A";
      if (dist(p, points[1]) < 15) dragTarget = "B";
    };

    canvas.onmousemove = (e) => {
      if (!dragTarget) return;
      const p = getCanvasXY(e);

      if (dragTarget === "A") points[0] = [p.x, p.y];
      if (dragTarget === "B") points[1] = [p.x, p.y];

      redrawFence();
    };

    canvas.onmouseup = () => {
      dragTarget = null;
    };
  }
  /* === 開始編輯模式 === */
  function beginEditFence(id, fences, panel) {
    const f = fences.find(x => x.id == id);
    if (!f) return;

    editingFence = f;

    panel.innerHTML = `
    <div class="fence-form">

      <label>Fence Name</label>
      <input id="editName" value="${f.name}">

      <label>Direction</label>
      <select id="editDir">
        <option value="AtoB" ${f.direction === "AtoB" ? "selected" : ""}>A → B</option>
        <option value="BtoA" ${f.direction === "BtoA" ? "selected" : ""}>B → A</option>
      </select>

      <label>Time</label>
      <div style="display:flex; gap:10px;">
        <input id="editStart" type="time" value="${f.start_time}">
        <input id="editEnd" type="time" value="${f.end_time}">
      </div>

      <div class="btn-area">
        <button id="saveEditBtn" class="btn btn-primary">Save</button>
        <button id="cancelEditBtn" class="btn btn-secondary">Cancel</button>
      </div>

    </div>
  `;

    document.getElementById("saveEditBtn").onclick =
      () => saveEditedFence(id, panel);

    document.getElementById("cancelEditBtn").onclick =
      () => reloadFenceList(panel);

    startDragModeForFence(f);
    applyTimePicker();
  }


  /* === 重載列表 === */
  async function reloadFenceList(panel) {
    const r = await fetch(`/api/fence/${currentType}?camera_id=${cameraId}`);
    const data = await r.json();
    renderFenceList(data, currentType, panel);
  }

  /* === 拖曳模式 === */
  function startDragModeForFence(f) {
    const videoW = imgStream.clientWidth;
    const videoH = imgStream.clientHeight;

    // 相對 → 絕對座標
    points = [
      [f.A[0] * videoW, f.A[1] * videoH],
      [f.B[0] * videoW, f.B[1] * videoH]
    ];

    redrawFence();

    canvas.onmousedown = (e) => {
      const p = getCanvasXY(e);
      if (dist(p, points[0]) < 15) dragTarget = "A";
      if (dist(p, points[1]) < 15) dragTarget = "B";
    };

    canvas.onmousemove = (e) => {
      if (!dragTarget) return;

      const p = getCanvasXY(e);
      if (dragTarget === "A") points[0] = [p.x, p.y];
      if (dragTarget === "B") points[1] = [p.x, p.y];

      redrawFence();
    };

    canvas.onmouseup = () => { dragTarget = null; };
  }

  /* === 工具函式 === */
  function getCanvasXY(e) {
    const r = canvas.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  }
  function dist(p, q) {
    return Math.sqrt((p.x - q[0]) ** 2 + (p.y - q[1]) ** 2);
  }

  function redrawFence() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    drawLine(points[0], points[1]);

    // 畫控制點
    drawHandle(points[0]);
    drawHandle(points[1]);
  }

  function drawHandle(pt) {
    ctx.fillStyle = "yellow";
    ctx.beginPath();
    ctx.arc(pt[0], pt[1], 6, 0, Math.PI * 2);
    ctx.fill();
  }
  async function saveNewFence() {
    const videoW = imgStream.clientWidth;
    const videoH = imgStream.clientHeight;

    const normA = [points[0][0] / videoW, points[0][1] / videoH];
    const normB = [points[1][0] / videoW, points[1][1] / videoH];

    const payload = {
      camera_id: cameraId,
      name: document.getElementById("newFenceName").value,
      direction: document.getElementById("newFenceDir").value,
      start_time: document.getElementById("newStart").value,
      end_time: document.getElementById("newEnd").value,
      point_a: normA,
      point_b: normB
    };

    await fetch(`/api/fence/${currentType}/add`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    await fetch(`/api/reload_gates/${cameraId}`, { method: "POST" });

    // 清畫面
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // 重載列表
    const panel = document.getElementById(`${currentType}_panel`);
    reloadFenceList(panel);
  }

  /* === Save 時一次更新：Name + Direction + Time + A/B 座標 === */
  async function saveEditedFence(id, panel) {
    const videoW = imgStream.clientWidth;
    const videoH = imgStream.clientHeight;

    const newA = [points[0][0] / videoW, points[0][1] / videoH];
    const newB = [points[1][0] / videoW, points[1][1] / videoH];

    const payload = {
      name: document.getElementById("editName").value,
      direction: document.getElementById("editDir").value,
      start_time: document.getElementById("editStart").value,
      end_time: document.getElementById("editEnd").value,
      A: newA,
      B: newB
    };

    await fetch(`/api/fence_update/${id}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    await fetch(`/api/reload_gates/${cameraId}`, { method: "POST" });

    reloadFenceList(panel);
  }


  /* === 畫線 + A/B 標示 === */
  function drawLine(p1, p2) {
    ctx.strokeStyle = "rgba(0,168,255,0.7)";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(p1[0], p1[1]);
    ctx.lineTo(p2[0], p2[1]);
    ctx.stroke();

    const midX = (p1[0] + p2[0]) / 2;
    const midY = (p1[1] + p2[1]) / 2;
    const dx = p2[0] - p1[0];
    const dy = p2[1] - p1[1];
    const len = Math.sqrt(dx * dx + dy * dy);
    const nx = -dy / len;
    const ny = dx / len;

    const offset = 25;
    const ax = midX + nx * offset;
    const ay = midY + ny * offset;
    const bx = midX - nx * offset;
    const by = midY - ny * offset;

    ctx.fillStyle = "#f1c40f";
    ctx.font = "bold 16px Arial";
    ctx.fillText("A", ax - 6, ay - 6);
    ctx.fillText("B", bx - 6, by - 6);
  }

  /* === 開啟新增圍籬表單 === */
  function openOnewayForm(points) {
    const panel = document.getElementById(`${currentType}_panel`);
    panel.innerHTML = `
      <div>
        <label>fence name</label>
        <input id="newFenceName">
        <label>Allow direction</label>
        <select id="newFenceDir">
          <option value="AtoB">A → B</option>
          <option value="BtoA">B → A</option>
        </select>
        <label>run time</label>
        <input id="newStart" type="time">
        <input id="newEnd" type="time">
        <button id="saveNewFenceBtn">儲存</button>
      </div>
    `;
    document.getElementById("saveNewFenceBtn").onclick = () => saveOnewayFence(points);
  }
  /* === People Counting 專用新增表單 === */
  function openCrowdFenceForm(points) {
    const panel = document.getElementById("crowd_panel");

    panel.innerHTML = `
    <div class="fence-form">
      <label>Fence Name</label>
      <input id="newCrowdName" placeholder="Enter fence name">

      <label>Direction</label>
      <select id="newCrowdDir">
        <option value="AtoB">A → B</option>
        <option value="BtoA">B → A</option>
      </select>

      <div class="btn-area">
        <button id="saveCrowdFenceBtn" class="btn btn-primary">Save</button>
        <button id="cancelCrowdFenceBtn" class="btn btn-secondary">Cancel</button>
      </div>
    </div>
  `;

    document.getElementById("saveCrowdFenceBtn").onclick =
      () => saveCrowdFence(points);

    document.getElementById("cancelCrowdFenceBtn").onclick =
      () => reloadFenceList(panel);
  }



  // === 更新時間排程到後端 ===
  async function updateSchedule(type) {
    const start = document.getElementById(`${type}-start`).value;
    const end = document.getElementById(`${type}-end`).value;

    const payload = {
      camera_id: cameraId,
      start_time: start,
      end_time: end,
    };

    console.log("更新排程:", payload);

    const res = await fetch(`/api/schedule/${type}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const result = await res.json();
    console.log("伺服器回應:", result);
  }

  async function toggleMode(type, enabled) {
    // === 1️⃣ 更新後端狀態 ===
    const res = await fetch(`/api/mode/${type}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        camera_id: cameraId,
        enabled: enabled,
      }),
    });
    const result = await res.json();
    console.log("Mode updated:", result);

    const camRes = await fetch(`/api/camera/${cameraId}`);
    const data = await camRes.json();
    const s = data.schedules || {};
    const sched = s[type] || { start: "00:00", end: "23:59" };

    const container =
      type === "climbing"
        ? document.getElementById("climb-time")
        : document.getElementById("fall-time");

    container.innerHTML = `
  <input type="text" id="${type}-start" class="time-input" value="${sched.start}">
  ~
  <input type="text" id="${type}-end" class="time-input" value="${sched.end}">
`;


    const startEl = document.getElementById(`${type}-start`);
    const endEl = document.getElementById(`${type}-end`);

    if (enabled) {
      startEl.disabled = false;
      endEl.disabled = false;
      startEl.addEventListener("change", () => updateSchedule(type));
      endEl.addEventListener("change", () => updateSchedule(type));
    } else {
      startEl.disabled = true;
      endEl.disabled = true;
    }
    flatpickr(".time-input", {
      enableTime: true,
      noCalendar: true,
      dateFormat: "H:i",
      time_24hr: true,
      onChange: function (selectedDates, dateStr, instance) {
        const id = instance.element.id; // e.g. climbing-start
        const type = id.split("-")[0];  // "climbing" or "falling"
        updateSchedule(type);
      }
    });

  }


  async function saveOnewayFence(points) {
    // 取得實際影像顯示尺寸
    const videoWidth = imgStream.clientWidth;
    const videoHeight = imgStream.clientHeight;

    // 將座標轉為相對比例（0~1）
    const normA = [points[0][0] / videoWidth, points[0][1] / videoHeight];
    const normB = [points[1][0] / videoWidth, points[1][1] / videoHeight];

    const payload = {
      camera_id: cameraId,
      name: document.getElementById("newFenceName").value,
      direction: document.getElementById("newFenceDir").value,
      start_time: document.getElementById("newStart").value,
      end_time: document.getElementById("newEnd").value,
      point_a: normA,
      point_b: normB,
    };

    const res = await fetch(`/api/fence/${currentType}/add`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const result = await res.json();

    if (result.status === "ok") {
      // ✅ 清空畫布
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      points = [];
      drawing = false;

      // ✅ 重新載入列表
      const panel = document.getElementById(`${currentType}_panel`);
      const r = await fetch(`/api/fence/${currentType}?camera_id=${cameraId}`);
      renderFenceList(await r.json(), currentType, panel);

      await fetch(`/api/reload_gates/${cameraId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ camera_id: cameraId })
      });
      console.log("新圍籬已儲存並清除畫布");
    }

  }

  async function saveCrowdFence(points) {
    const videoWidth = imgStream.clientWidth;
    const videoHeight = imgStream.clientHeight;

    const normA = [points[0][0] / videoWidth, points[0][1] / videoHeight];
    const normB = [points[1][0] / videoWidth, points[1][1] / videoHeight];

    const payload = {
      camera_id: cameraId,
      name: document.getElementById("newCrowdName").value,
      direction: document.getElementById("newCrowdDir").value,
      point_a: normA,
      point_b: normB
    };

    const res = await fetch(`/api/fence/crowd/add`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const result = await res.json();
    if (result.status === "ok") {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      points = [];
      drawing = false;
      const panel = document.getElementById("crowd_panel");
      const r = await fetch(`/api/fence/crowd?camera_id=${cameraId}`);
      renderFenceList(await r.json(), "crowd", panel);
      await fetch(`/api/reload_gates/${cameraId}`, { method: "POST" });
      console.log("📊 People Counting Fence 已儲存");
    }
  }

  // flatpickr("input[type='time']", {
  //   enableTime: true,
  //   noCalendar: true,
  //   dateFormat: "H:i",
  //   time_24hr: true,
  // });
};
window.switchTab = function (tab) {
  const info = document.getElementById("panel-info");
  const func = document.getElementById("panel-functions");

  const t1 = document.getElementById("tab-info");
  const t2 = document.getElementById("tab-functions");

  if (tab === "info") {
    info.classList.remove("hidden");
    func.classList.add("hidden");

    t1.classList.add("active");
    t2.classList.remove("active");
  } else {
    func.classList.remove("hidden");
    info.classList.add("hidden");

    t2.classList.add("active");
    t1.classList.remove("active");
  }
}

window.saveCameraInfo = async function () {
  const payload = {
    id: cameraId,
    name: document.getElementById("cam-name").value,
    location: document.getElementById("cam-location").value
  };

  await fetch("/api/camera/update", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  document.getElementById("cameraTitle").textContent = name;
  alert("Camera info updated!");
};