window.onload = async function () {
  const video = document.getElementById("cameraVideo");
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

    console.log("✅ Loaded camera data:", data);

    if (data.error) {
      alert("Camera not found");
      return;
    }

    // 顯示影片
    document.getElementById("cameraTitle").textContent = data.camera_name;
    video.src = data.camera_url;

    // === 綁定開關 ===
    const climbSwitch = document.getElementById("climb-switch");
    const fallSwitch = document.getElementById("fall-switch");

    console.log("Found climbSwitch:", !!climbSwitch, "fallSwitch:", !!fallSwitch);

    climbSwitch.checked = Boolean(data.climbing_detection_mode);
    fallSwitch.checked = Boolean(data.falling_detection_mode);

    console.log("🎯 climb:", climbSwitch.checked, "fall:", fallSwitch.checked);

    // === 顯示時間 ===
    const s = data.schedules || {};
    document.getElementById("climb-time").textContent =
      data.climbing_detection_mode && s.climbing
        ? `[${s.climbing.start} ~ ${s.climbing.end}]`
        : "[--:-- ~ --:--]";

    document.getElementById("fall-time").textContent =
      data.falling_detection_mode && s.falling
        ? `[${s.falling.start} ~ ${s.falling.end}]`
        : "[--:-- ~ --:--]";
  }

  await loadCamera();

  /* === 監聽所有 fence-btn === */
  document.querySelectorAll(".fence-btn").forEach(btn => {
    btn.addEventListener("click", async () => {
      const type = btn.dataset.type;
      currentType = type;
      const panel = document.getElementById(`${type}_panel`);
      panel.classList.toggle("hidden");

      if (!panel.classList.contains("hidden")) {
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
    // if (!currentType) return alert("請先選擇要新增的功能！");
    points = [];
    video.pause();

    canvas.width = video.clientWidth;
    canvas.height = video.clientHeight;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    drawing = true;
    // alert("📸 點擊兩點以建立圍籬線");
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
      openFenceForm(points);
    } else {
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
  function openFenceForm(points) {
    const panel = document.getElementById(`${currentType}_panel`);
    panel.innerHTML = `
      <div>
        <label>fence name</label>
        <input id="newFenceName">
        <label>direction</label>
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
    document.getElementById("saveNewFenceBtn").onclick = () => saveFence(points);
  }

  /* === 儲存圍籬 === */
  async function saveFence(points) {
    const payload = {
      camera_id: cameraId,
      name: document.getElementById("newFenceName").value,
      direction: document.getElementById("newFenceDir").value,
      start_time: document.getElementById("newStart").value,
      end_time: document.getElementById("newEnd").value,
      point_a: points[0],
      point_b: points[1],
    };

    const res = await fetch(`/api/fence/${currentType}/add`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await res.json();

    if (result.status === "ok") {
      // alert("✅ 新圍籬已儲存！");
      const panel = document.getElementById(`${currentType}_panel`);
      const r = await fetch(`/api/fence/${currentType}?camera_id=${cameraId}`);
      renderFenceList(await r.json(), currentType, panel);
    } else {
      // alert("❌ 錯誤：" + result.message);
    }
  }
};
