window.onload = async function () {
  const imgStream = document.getElementById("videoStream");
  const canvas = document.getElementById("drawCanvas");
  const ctx = canvas.getContext("2d");

  let drawing = false;
  let points = [];
  let currentType = null;

  const params = new URLSearchParams(window.location.search);
  const cameraId = params.get("id");

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

  /* === 顯示圍籬列表 === */
  function renderFenceList(fences, type, panel) {
    panel.innerHTML = "";
    const list = document.createElement("div");

    if (fences.length === 0) {
      const msg = document.createElement("div");
      // msg.textContent = "目前尚無圍籬設定。";
      msg.style.color = "#666";
      msg.style.marginBottom = "8px";
      list.appendChild(msg);
    } else {
      fences.forEach(f => {
        const item = document.createElement("div");
        item.textContent = `${f.name} (${f.direction}) [${f.start_time}~${f.end_time}]`;
        list.appendChild(item);
      });
    }

    const addBtn = document.createElement("button");
    addBtn.textContent = "+ Add Fence";
    addBtn.onclick = startDrawing;
    panel.appendChild(list);
    panel.appendChild(addBtn);
  }

  /* === 畫線 === */
  function startDrawing() {
    points = [];
    canvas.width = imgStream.clientWidth;
    canvas.height = imgStream.clientHeight;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    drawing = true;
    console.log("開始框選:", currentType);
  }


  canvas.addEventListener("click", (e) => {
    if (!drawing) return;

    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    points.push([x, y]);

    if (points.length === 2) {
      drawing = false;
      drawLine(points[0], points[1]);

      // 根據 currentType 決定開哪一個表單
      if (currentType === "crowd") {
        openCrowdFenceForm(points);
      } else {
        openOnewayForm(points);
      }
    } else {
      // 畫第一個點的黃色標記
      ctx.fillStyle = "yellow";
      ctx.beginPath();
      ctx.arc(x, y, 4, 0, 2 * Math.PI);
      ctx.fill();
    }
  });

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
      <input id="newCrowdName" placeholder="Enter name">

      <label>Direction</label>
      <select id="newCrowdDir">
        <option value="AtoB">A → B</option>
        <option value="BtoA">B → A</option>
      </select>

      <button id="saveCrowdFenceBtn">儲存</button>
    </div>
  `;
    document.getElementById("saveCrowdFenceBtn").onclick = () => saveCrowdFence(points);
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

