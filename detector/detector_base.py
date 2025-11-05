# detector/detector_base.py
# 偵測模組的抽象基底
from abc import ABC, abstractmethod

class DetectorBase(ABC):
    def __init__(self, camera_id):
        self.camera_id = camera_id
        self.running = True

    @abstractmethod
    def run(self):
        pass

    def stop(self):
        self.running = False
