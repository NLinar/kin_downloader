from PyQt5.QtCore import QObject, pyqtSignal
import time

class Worker(QObject):
    progress_signal = pyqtSignal(int, int)
    status_signal = pyqtSignal(int, str)
    finished_signal = pyqtSignal(bool)

    def __init__(self, not_downloaded_files, stop_event):
        super().__init__()
        self.not_downloaded_files = not_downloaded_files
        self.stop_event = stop_event

    def run(self):
        try:
            self.finished_signal.emit(False)
            for file_index, entry in self.not_downloaded_files:
                if self.stop_event.is_set():
                    return
                for i in range(1, 51):
                    if self.stop_event.is_set():
                        return
                    self.progress_signal.emit(file_index, i * 2)
                    time.sleep(0.1)
                if self.stop_event.is_set():
                    return
                self.status_signal.emit(file_index, "Декодирование")
                time.sleep(2)
                if self.stop_event.is_set():
                    return
                self.status_signal.emit(file_index, "Объединение")
                time.sleep(2)
                if self.stop_event.is_set():
                    return
                self.status_signal.emit(file_index, "Загружено")
                time.sleep(2)
            self.finished_signal.emit(True)
        except Exception as e:
            print(f"Error_downloader: {e}")
