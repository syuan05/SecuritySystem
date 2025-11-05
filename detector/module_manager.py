# detector/module_manager.py
from detector.drawer import Drawer
from detector.modules.inout_module import InOutModule
# from detector.modules.people_flow_module import PeopleFlowModule
# from detector.modules.fall_module import FallModule
# from detector.modules.climb_module import ClimbModule
from db_utils import get_db_connection

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

        if "in_out_control" in funcs:
            self.modules.append(InOutModule(self.camera_id))
        # if "crowd_count" in funcs:
        #     self.modules.append(PeopleFlowModule(self.camera_id))

    # def _load_always_on_modules(self):
        # self.modules.append(FallModule(self.camera_id))
        # self.modules.append(ClimbModule(self.camera_id))
    def process(self, frame):
        results = []
        gates = []  # 保證變數一定存在

        for m in self.modules:
            # 先收集所有模組的 gate 設定
            if hasattr(m, "gates"):
                gates.extend(m.gates)

            # 執行分析
            mod_results = m.analyze(frame)
            if mod_results:
                results.extend(mod_results)

        # ✅ 即使沒有模組也不會出錯
        return self.drawer.draw(frame, self.camera_id, results, gates)
