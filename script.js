// script.js
import { db } from "./firebase.js";
import { collection, getDocs } from "https://www.gstatic.com/firebasejs/10.12.0/firebase-firestore.js";

// 🔹 找到要放攝影機卡片的容器
const cameraList = document.getElementById("cameraList");

// 🔹 從 Firestore 讀取 cameras 集合
async function loadCameras() {
  const querySnapshot = await getDocs(collection(db, "cameras"));
  cameraList.innerHTML = "";
  querySnapshot.forEach((docSnap) => {
    const data = docSnap.data();
    addCamera(docSnap.id, data.name, data.video_url);
  });
}

// 🔹 建立影片卡片
function addCamera(id, name, src) {
  const card = document.createElement("div");
  card.className = "camera-card";
  card.innerHTML = `
    <video src="${src}" controls></video>
    <h3>${name}</h3>
    <a href="camera.html?id=${id}" class="view-btn">view</a>
  `;
  cameraList.appendChild(card);
}

// 🔹 初始化
loadCameras();
