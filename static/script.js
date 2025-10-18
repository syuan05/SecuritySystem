// 🔹 找到要放攝影機卡片的容器
const cameraList = document.getElementById("cameraList");

// 🔹 主函式：從 Flask API 讀取 cameras 並顯示
async function loadCameras() {
  try {
    const res = await fetch("/api/cameras");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const cameras = await res.json();

    // 清空畫面
    cameraList.innerHTML = "";

    if (cameras.length === 0) {
      cameraList.innerHTML = `<p>No cameras found.</p>`;
      return;
    }

    // 動態建立每個攝影機卡片
    cameras.forEach((cam) => addCameraCard(cam));
  } catch (err) {
    console.error("❌ Failed to load cameras:", err);
    cameraList.innerHTML = `<p style="color:red;">Failed to load cameras.</p>`;
  }
}

// 🔹 建立攝影機卡片
function addCameraCard(cam) {
  console.log(cam); // ← debug：你會看到 camera_id / camera_name / camera_url

  const card = document.createElement("div");
  card.className = "camera-card";
  card.innerHTML = `
    <div class="camera-info">
      <h3>${cam.camera_name}</h3>
      <video src="${cam.camera_url}" controls muted preload="metadata"></video>
    </div>
    <div class="camera-actions">
      <a href="/camera.html?id=${cam.camera_id}" class="view-btn">View</a>
    </div>
  `;
  cameraList.appendChild(card);
}

// 🔹 頁面初始化
document.addEventListener("DOMContentLoaded", loadCameras);
