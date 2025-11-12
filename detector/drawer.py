import cv2
import time
import cv2 as cv
from detector.event_bus import event_bus


class Drawer:
    def draw(self, frame, camera_id, module_results, gates=None):
        frame = frame.copy()
        # ==================================================
        # 1️⃣ 畫 YOLO 偵測框與腳底點
        # ==================================================
        for r in module_results:
            if "bbox" in r:
                x1, y1, x2, y2 = r["bbox"]
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                if "foot" in r:
                    cv2.circle(frame, r["foot"], 4, (0, 0, 255), -1)

        # ==================================================
        # 2️⃣ 根據 EventBus 狀態決定顏色
        # ==================================================
        state = event_bus.get_state(camera_id)

        # ==================================================
        # 3️⃣ 畫門線（含 camera_id 過濾）
        # ==================================================
        drawn_count = 0
        skipped_count = 0
        if gates:
            for g in gates:
                gate_camera_id = g.get("camera_id")
                if gate_camera_id is None:
                    print(f"[WARN] Camera {camera_id}: Gate '{g.get('name', 'Unknown')}' (ID:{g.get('id')}) missing camera_id, skipping")
                    skipped_count += 1
                    continue
                if gate_camera_id != camera_id:
                    print(f"[WARN] Camera {camera_id}: Skipping gate '{g['name']}' (belongs to camera {gate_camera_id})")
                    skipped_count += 1
                    continue

                color = state["gates"].get(g["id"], {}).get("color", (0, 168, 255))
                cv2.line(frame, g["a"], g["b"], color, 3)
                mid = ((g["a"][0] + g["b"][0]) // 2, (g["a"][1] + g["b"][1]) // 2)
                cv2.putText(frame, g["name"], mid, cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                drawn_count += 1

        # ==================================================
        # 4️⃣ 畫人物資訊（腳底點）
        # ==================================================
        for tid, info in state.get("people", {}).items():
            color = info.get("color", (0, 255, 0))
            if "foot" in info:
                cv2.circle(frame, info["foot"], 4, color, -1)

        # ==================================================
        # 5️⃣ 顯示統計資訊（人流統計）
        # ==================================================
        total = state.get("person_total", {})
        gate_counts = state.get("gate_counts", {})
        from detector.video_manager import manager_instance
        worker = manager_instance.workers.get(camera_id)
        modules = worker["modules"].modules if worker else []
        has_person_module = any(m.__class__.__name__ == "PersonCountModule" for m in modules)

        if not has_person_module:
            return frame
        
        y = 30
        cv2.putText(frame,
                    f"Total In: {total.get('in', 0)}    Total Out: {total.get('out', 0)}",
                    (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        y += 25

        for gid, info in gate_counts.items():
            cv2.putText(frame,
                        f"Gate{gid} In: {info.get('in', 0)}   Out: {info.get('out', 0)}",
                        (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 255, 200), 1)
            y += 20

        # ==================================================
        # 6️⃣ 顯示視窗（除非 Flask 模式）
        # ==================================================
        win_name = f"camera_{camera_id}"
        cv.imshow(win_name, frame)
        cv.waitKey(1)
        return frame

    # ==================================================
    # 🟡 新增：單純畫出所有門線（不依賴模組結果）
    # ==================================================
    def draw_gates_only(self, frame, gates):
        """
        用於 reload 後立即重畫門線。
        """
        frame = frame.copy()
        for g in gates:
            color = (0, 168, 255)
            cv2.line(frame, g["a"], g["b"], color, 3)
            mid = ((g["a"][0] + g["b"][0]) // 2, (g["a"][1] + g["b"][1]) // 2)
            cv2.putText(frame, g["name"], mid, cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        win_name = "reload_preview"
        cv.imshow(win_name, frame)
        cv.waitKey(1)
        return frame
