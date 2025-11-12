# detector/module_manager.py
from detector.drawer import Drawer
from detector.modules.inout_module import InOutModule
from detector.modules.person_count import PersonCountModule
# from detector.modules.fall_module import FallModule
# from detector.modules.climb_module import ClimbModule
from db_utils import get_db_connection
import numpy as np

class ModuleManager:
    def __init__(self, camera_id, camera_url):
        self.camera_id = camera_id
        self.camera_url = camera_url
        self.modules = []
        self._load_dynamic_modules()
        # self._load_always_on_modules()
        self.drawer = Drawer()

    def _load_dynamic_modules(self):
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT DISTINCT function_type
            FROM func_schedules s
            JOIN gates g ON s.gate_id=g.gate_id
            WHERE s.camera_id=%s AND s.is_active=1
        """, (self.camera_id,))
        funcs = [r["function_type"] for r in cur.fetchall()]
        cur.close(); conn.close()
        # ✅ 初始化統計數值
        inout_count = 0
        person_count = 0
        inout_names = []
        person_names = []

        # === 根據功能類型載入模組 ===
        if "in_out_control" in funcs:
            try:
                inout_mod = InOutModule(self.camera_id)
                self.modules.append(inout_mod)
                inout_count = len(inout_mod.gates)
                inout_names = [g["name"] for g in inout_mod.gates]
            except Exception as e:
                print(f"[WARN] Camera {self.camera_id}: failed to load InOutModule ({e})")

        if "person_count" in funcs:
            try:
                pf_mod = PersonCountModule(self.camera_id)
                self.modules.append(pf_mod)
                person_count = len(pf_mod.gates)
                person_names = [g["name"] for g in pf_mod.gates]
                from detector.event_bus import event_bus
                gate_ids = [g["id"] for g in pf_mod.gates]
                event_bus.ensure_person_count_init(self.camera_id, gate_ids)
            except Exception as e:
                print(f"[WARN] Camera {self.camera_id}: failed to load PersonCountModule ({e})")

        # === ✅ 安全輸出 log ===
        print(f"[INIT] Camera {self.camera_id}: "
            f"{inout_count} InOut gates {inout_names}, "
            f"{person_count} PersonCount gates {person_names}.")
    # def _load_always_on_modules(self):
        # self.modules.append(FallModule(self.camera_id))
        # self.modules.append(ClimbModule(self.camera_id))
    def process(self, frame, camera_id=None):
        cam_id = camera_id or self.camera_id
        results = []
        gates = []
        drawn = frame

        for m in self.modules:
            if hasattr(m, "gates"):
                gates.extend([g for g in m.gates if g.get("camera_id") == self.camera_id])
            mod_results = m.analyze(drawn)
            if isinstance(mod_results, list):
                results.extend(mod_results)
            # 如果模組直接回傳畫面（極少數情況），只在沒有結果時使用
            elif isinstance(mod_results, (np.ndarray)) and len(results) == 0:
                drawn = mod_results
        gates = [g for g in gates if g.get("camera_id") == self.camera_id]
        return self.drawer.draw(drawn, self.camera_id, results, gates)