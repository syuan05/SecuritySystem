# detector/drawer.py
import cv2
import time
import cv2 as cv
from detector.event_bus import event_bus

class Drawer:
    def draw(self, frame, camera_id, module_results, gates=None):
        frame = frame.copy()
        # ==================================================
        # 1️⃣ 先畫模組原本的結果（YOLO 偵測框與腳底點）
        # ==================================================
        for r in module_results:
            if "bbox" in r:
                x1, y1, x2, y2 = r["bbox"]
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                if "foot" in r:
                    cv2.circle(frame, r["foot"], 4, (0, 0, 255), -1)

        # ==================================================
        # 2️⃣ 根據 EventBus 狀態改顏色
        # ==================================================
        state = event_bus.get_state(camera_id)

        # ==================================================
        # 3️⃣ 畫門線（✅ 加入過濾邏輯）
        # ==================================================
        drawn_count = 0      # ✅ 統計實際畫了幾條線
        skipped_count = 0    # ✅ 統計跳過幾條線
        
        if gates:
            for g in gates:
                # ✅ 防呆檢查 1: gate 必須有 camera_id 欄位
                gate_camera_id = g.get("camera_id")
                
                if gate_camera_id is None:
                    print(f"[WARN] Camera {camera_id}: Gate '{g.get('name', 'Unknown')}' (ID:{g.get('id')}) missing camera_id, skipping")
                    skipped_count += 1
                    continue
                
                # ✅ 防呆檢查 2: gate 的 camera_id 必須等於當前 camera_id
                if gate_camera_id != camera_id:
                    print(f"[WARN] Camera {camera_id}: Skipping gate '{g['name']}' (belongs to camera {gate_camera_id})")
                    skipped_count += 1
                    continue
                
                # ✅ 通過檢查，開始畫線
                color = state["gates"].get(g["id"], {}).get("color", (0, 168, 255))
                cv2.line(frame, g["a"], g["b"], color, 3)
                mid = ((g["a"][0] + g["b"][0]) // 2, (g["a"][1] + g["b"][1]) // 2)
                cv2.putText(frame, g["name"], mid, cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                drawn_count += 1
                # print(f"[DRAWER] Camera {camera_id} drew gate '{g['name']}' from {g['a']} to {g['b']}")
        
        # ✅ 輸出統計
        # if gates:
        #     print(f"[DRAWER] Camera {camera_id}: drew {drawn_count} gates, skipped {skipped_count} gates (total {len(gates)} gates received)")
        # else:
        #     print(f"[DRAWER] Camera {camera_id}: no gates to draw")
        
        # ==================================================
        # 4️⃣ 畫人物資訊（防止 'people' key 缺失）
        # ==================================================
        for tid, info in state.get("people", {}).items():
            color = info.get("color", (0, 255, 0))
            if "foot" in info:
                cv2.circle(frame, info["foot"], 4, color, -1)

        # ==================================================
        # 5️⃣ 顯示統計資訊（僅當人流模組啟動時）
        # ==================================================
        total = state.get("people_total", {})
        gate_counts = state.get("gate_counts", {})

        has_person_count = (
            (total.get("in", 0) > 0 or total.get("out", 0) > 0) or
            len(gate_counts) > 0
        )

        if has_person_count:
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
        # if gates:
        #     gate_names = [g["name"] for g in gates if g.get("camera_id") == camera_id]
        #     if gate_names:
        #         print(f"[DRAWER] Camera {camera_id} drew {len(gate_names)} gates: {', '.join(gate_names)}")
        #     else:
        #         print(f"[DRAWER] Camera {camera_id} drew no gates (after filtering)")
        # else:
        #     print(f"[DRAWER] Camera {camera_id} drew no gates (none provided)")
        # win_name = f"camera_{camera_id}"
        # cv.imshow(win_name, frame)
        # cv.waitKey(1)
        # print(f"[DRAWER] ✅ returning frame for camera {camera_id}")
        return frame