import cv2
import time
import cv2 as cv
from detector.event_bus import event_bus
import math

class Drawer:
    def draw(self, frame, camera_id, module_results, gates=None, gate_name_map=None):
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

                gate_type = g.get("type", "inout")

                if gate_type == "person":
                    default_color = (0, 168, 255)   # 🟡 黃色

                else:
                    default_color = (0, 255, 0)     # 🟢 綠色

                color = state["gates"].get(g["id"], {}).get("color", default_color)
                cv2.line(frame, g["a"], g["b"], color, 3)
                mid = ((g["a"][0] + g["b"][0]) // 2, (g["a"][1] + g["b"][1]) // 2)

                # ✅ 計算門線的垂直方向
                ax, ay = g["a"]
                bx, by = g["b"]
                # 門線向量
                dx, dy = bx - ax, by - ay
                # 正規化
                length = math.sqrt(dx*dx + dy*dy)
                if length > 0:
                    dx, dy = dx/length, dy/length
                # 垂直向量（左手法向量）
                nx, ny = dy, -dx  

                # ✅ 根據 in_dir 決定箭頭方向
                in_dir = g.get("in_dir", 1)
                if in_dir == -1:
                    nx, ny = -nx, -ny  # 反轉方向

                arrow_len = 40  # 箭頭主幹長度
                arrow_head = 12  # 箭頭頭部長度
                arrow_tail = 20  # ✅ 新增：箭頭尾部長度（門線後方延伸）

                # 箭頭起點（門線後方）
                start_x = int(mid[0] - nx * arrow_tail)
                start_y = int(mid[1] - ny * arrow_tail)

                # 箭頭終點（門線前方）
                end_x = int(mid[0] + nx * arrow_len)
                end_y = int(mid[1] + ny * arrow_len)

                # 主幹（穿越門線）
                cv2.line(frame, (start_x, start_y), (end_x, end_y), (255, 255, 255), 2)

                # 箭頭兩側（維持不變）
                head_angle = 0.5
                left_x = int(end_x - nx * arrow_head + ny * arrow_head * head_angle)
                left_y = int(end_y - ny * arrow_head - nx * arrow_head * head_angle)
                right_x = int(end_x - nx * arrow_head - ny * arrow_head * head_angle)
                right_y = int(end_y - ny * arrow_head + nx * arrow_head * head_angle)

                cv2.line(frame, (end_x, end_y), (left_x, left_y), (255, 255, 255), 2)
                cv2.line(frame, (end_x, end_y), (right_x, right_y), (255, 255, 255), 2)

                # 門線名稱（標在箭頭起點附近，稍微偏移避免重疊）
                # ====== 門線名稱：框右邊對齊門線右端 ======
                text = g["name"]
                (font_w, font_h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)

                # 找出門線最右側的 x 座標（靠右對齊）
                right_x = max(g["a"][0], g["b"][0])

                # 框的 padding
                pad = 6
                offset_y = -10  # 微上移讓位置更自然

                # 框右邊對齊門線右端：rect_x2 = right_x
                rect_x2 = right_x
                rect_x1 = rect_x2 - (font_w + pad*2)

                # 垂直位置（以門線中點為基準）
                mid_y = (g["a"][1] + g["b"][1]) // 2
                rect_y1 = mid_y - font_h - pad + offset_y
                rect_y2 = mid_y + pad + offset_y

                # 畫白底黑邊框
                cv2.rectangle(frame, (rect_x1, rect_y1), (rect_x2, rect_y2), (255,255,255), -1)
                cv2.rectangle(frame, (rect_x1, rect_y1), (rect_x2, rect_y2), (0,0,0), 2)

                # 文字位置（從框內左上方 + padding）
                text_x = rect_x1 + pad
                text_y = rect_y2 - pad

                cv2.putText(frame, text, (text_x, text_y),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,0,0), 2)
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

        if not gate_counts:
            return frame

        # 建立所有行（分 total 與 gate）
        lines = []

        # 第一行 Total
        total_text = f"Total In: {total.get('in',0)}    Total Out: {total.get('out',0)}"
        lines.append(("total", total_text))

        # gate 行
        gate_name_map = gate_name_map or {}
        for gid, info in gate_counts.items():
            name = gate_name_map.get(gid, f"Gate{gid}")
            gate_text = f"{name}: In {info.get('in',0)}  /  Out {info.get('out',0)}"
            lines.append(("gate", gate_text))


        # ====== 計算最大寬度（重要：兩種字體都算） ======
        max_width = 0
        for ttype, text in lines:
            if ttype == "total":
                (w, h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            else:
                (w, h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
            max_width = max(max_width, w)


        # ====== 畫大框 ======
        x0, y0 = 15, 10
        padding = 10
        line_height = 22

        box_width  = max_width + padding*2
        box_height = line_height * len(lines) + padding

        cv2.rectangle(frame,
                    (x0, y0),
                    (x0 + box_width, y0 + box_height),
                    (0, 0, 0), -1)

        # ====== 寫文字 ======
        y = y0 + 20
        for ttype, text in lines:
            cv2.putText(frame, text, (x0 + padding, y),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1)
            y += line_height


        # === Gate In/Out ===
        gate_name_map = gate_name_map or {}


        timestamp = time.strftime("%Y.%m.%d %H:%M:%S")
        cam_name = f"Camera {camera_id}" if not isinstance(camera_id, str) else camera_id
        text = f"{timestamp}  -  {cam_name}"

        (h, w) = frame.shape[:2]

        cv2.putText(frame,
                    text,
                    (w - 10 - cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)[0][0],
                    h - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (255, 255, 255),
                    2)
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
