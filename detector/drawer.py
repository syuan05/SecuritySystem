# detector/drawer.py
import cv2
from detector.event_bus import event_bus

class Drawer:
    def draw(self, frame, camera_id, module_results, gates=None):
        # 1️⃣ 先畫模組原本的結果
        for r in module_results:
            if "bbox" in r:
                x1,y1,x2,y2 = r["bbox"]
                cv2.rectangle(frame, (x1,y1), (x2,y2), (0,255,0), 2)
                if "foot" in r:
                    cv2.circle(frame, r["foot"], 4, (0,0,255), -1)

        # 2️⃣ 根據 EventBus 狀態改顏色
        import time
        state = event_bus.get_state(camera_id)
        gate_colors = {}
        for gid, info in state["gates"].items():
            color = info["color"]
            ts = info.get("timestamp", 0)
            if time.time() - ts > 1.5:  # 超過 1.5 秒自動恢復
                color = (0, 168, 255)  # 橘色（預設）
            gate_colors[gid] = color

        # 畫門線：若有事件就用對應顏色，否則用預設橘色
        if gates:
            for g in gates:
                color = gate_colors.get(g["id"], (0, 168, 255))  # 預設橘色
                cv2.line(frame, g["a"], g["b"], color, 3)
                mid = ((g["a"][0] + g["b"][0]) // 2, (g["a"][1] + g["b"][1]) // 2)
                cv2.putText(frame, g["name"], mid,
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)


        # --- 人框上色 (假設有 tracking ID) ---
        for tid, info in state["people"].items():
            color = info["color"]
            # 這裡可以在人物框或腳底標示顏色
            # cv2.rectangle(frame, bbox_top_left, bbox_bottom_right, color, 2)

        # --- 左上角人流統計 ---
        # c = state["count"]
        # txt = f"IN:{c.get('in',0)} OUT:{c.get('out',0)} NOW:{c.get('now',0)}"
        # cv2.putText(frame, txt, (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 2)

        cv2.imshow(f"Camera {camera_id}", frame)
        cv2.waitKey(1)
        return frame
