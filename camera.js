// camera.js
import { db } from "./firebase.js";
import {
  doc,
  getDoc,
  updateDoc,
  arrayUnion,  // 🔹 新增這個用來 push 陣列項目
} from "https://www.gstatic.com/firebasejs/10.12.0/firebase-firestore.js";

const video = document.getElementById("cameraVideo");
const canvas = document.getElementById("drawCanvas");
const ctx = canvas.getContext("2d");

let drawing = false;
let points = [];
let currentFenceType = null;
let currentCameraId = null;

// 🔹 取得 URL 中的 id，例如 camera.html?id=camera_1
const params = new URLSearchParams(window.location.search);
currentCameraId = params.get("id");

// 🔹 從 Firestore 載入影片資料
async function loadCamera() {
  if (!currentCameraId) return;
  const camRef = doc(db, "cameras", currentCameraId);
  const camSnap = await getDoc(camRef);

  if (camSnap.exists()) {
    const data = camSnap.data();
    document.getElementById("cameraTitle").textContent = data.name;
    video.src = data.video_url;
  }
}

// 🔹 畫線功能：暫停影片 → 擷取畫面
function startDrawing(type) {
  currentFenceType = type;
  points = [];

  // 暫停影片
  video.pause();

  // 畫出當前畫面
  const vw = video.clientWidth;
  const vh = video.clientHeight;
  canvas.width = vw;
  canvas.height = vh;
  ctx.drawImage(video, 0, 0, vw, vh);

  drawing = true;
  alert("📸 Video paused — click two points to mark the fence line.");
}

// 🔹 點擊畫線
canvas.addEventListener("click", (e) => {
  if (!drawing) return;

  const rect = canvas.getBoundingClientRect();
  const x = e.clientX - rect.left;
  const y = e.clientY - rect.top;
  points.push([x, y]);

  if (points.length === 2) {
    drawing = false;
    drawLine(points[0], points[1]);
  } else {
    ctx.fillStyle = "yellow";
    ctx.beginPath();
    ctx.arc(x, y, 4, 0, 2 * Math.PI);
    ctx.fill();
  }
});

// 🔹 畫線 + A/B 在兩側
function drawLine(p1, p2) {
  const color = currentFenceType === "gate" ? "#00a8ff" : "#e67e22";

  // 主線
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(p1[0], p1[1]);
  ctx.lineTo(p2[0], p2[1]);
  ctx.stroke();

  // 計算線的中點和法向量（垂直方向）
  const midX = (p1[0] + p2[0]) / 2;
  const midY = (p1[1] + p2[1]) / 2;
  const dx = p2[0] - p1[0];
  const dy = p2[1] - p1[1];
  const length = Math.sqrt(dx * dx + dy * dy);
  const nx = -dy / length;
  const ny = dx / length;

  // 左右側偏移
  const offset = 15;
  const ax = midX + nx * offset;
  const ay = midY + ny * offset;
  const bx = midX - nx * offset;
  const by = midY - ny * offset;

  ctx.fillStyle = "#f1c40f";
  ctx.font = "16px Arial";
  ctx.fillText("A", ax - 6, ay - 6);
  ctx.fillText("B", bx - 6, by - 6);
}

// 🔹 寫入 Firestore
async function saveFence(type) {
  if (points.length < 2) return alert("請先畫出線段再儲存");

  const name = document.getElementById(`${type}_name`)?.value || "Fence";
  const direction = document.getElementById(`${type}_dir`)?.value || "A->B";
  const start = document.getElementById(`${type}_start`)?.value || "";
  const end = document.getElementById(`${type}_end`)?.value || "";

  const newFence = {
    name,
    direction,
    type,
    time_start: start,
    time_end: end,
    points, // [[x1, y1], [x2, y2]]
    createdAt: new Date().toISOString(),
  };

  const camRef = doc(db, "cameras", currentCameraId);
  await updateDoc(camRef, {
    fences: arrayUnion(newFence), // ✅ Firestore 陣列新增
  });

  alert("✅ Fence saved to Firestore!");
  drawing = false;
}

// 🔹 刪除圍籬
async function deleteFence(type) {
  alert("🚫 Firestore 無法直接刪除陣列中的特定項目，請改用後端或重新覆寫 fences 欄位。");
}

// 🔹 展開面板
function showFencePanel(panelId, type) {
  const panel = document.getElementById(panelId);
  panel.innerHTML = `
    <input id="${type}_name" placeholder="Fence Name">
    <select id="${type}_dir">
      <option value="A->B">A → B</option>
      <option value="B->A">B → A</option>
    </select>
    <label>Start Time</label>
    <input type="time" id="${type}_start">
    <label>End Time</label>
    <input type="time" id="${type}_end">
    <button id="${type}_add">Add New Fence</button>
    <button id="${type}_save">Save</button>
  `;
  panel.classList.toggle("hidden");

  document.getElementById(`${type}_add`).onclick = () => startDrawing(type);
  document.getElementById(`${type}_save`).onclick = () => saveFence(type);
}

// 🔹 防止跳頁
document.getElementById("gate_recordBtn").addEventListener("click", (e) => {
  e.preventDefault();
  showFencePanel("gate_panel", "gate");
});
document.getElementById("crowd_countBtn").addEventListener("click", (e) => {
  e.preventDefault();
  showFencePanel("crowd_panel", "crowd");
});

// 初始化
loadCamera();
