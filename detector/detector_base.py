# detector/detector_base.py
from abc import ABC, abstractmethod

class DetectorBase(ABC):
    def __init__(self, camera_id, camera_url):
        self.camera_id = camera_id
        self.camera_url = camera_url
        self.running = True

    @abstractmethod
    def run(self):
        pass

    def stop(self):
        self.running = False
