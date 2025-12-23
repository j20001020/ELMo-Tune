import psutil
import threading

from utils.utils import log_update

class ResourceMonitor:
    def __init__(self, process):
        self.process = process
        self.cpu_usage = []
        self.mem_usage = []
        self._stop_event = threading.Event()
        self.monitor_thread = threading.Thread(target=self._monitor)

    def _monitor(self):
        try:
            while not self._stop_event.is_set() and self.process.is_running():
                try:
                    # CPU usage as a percentage
                    self.cpu_usage.append(self.process.cpu_percent(interval=1))
                    # Memory usage in MB
                    self.mem_usage.append(self.process.memory_info().rss / (1024 * 1024))
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    break
        except Exception as e:
            log_update(f"[RM] Monitoring error: {e}")

    def start_monitor(self):
        self.monitor_thread.start()

    def stop_monitor(self):
        self._stop_event.set()
        self.monitor_thread.join()
        avg_cpu = sum(self.cpu_usage) / len(self.cpu_usage) if self.cpu_usage else 0.0
        avg_mem = sum(self.mem_usage) / len(self.mem_usage) if self.mem_usage else 0.0
        return avg_cpu, avg_mem