from PyQt5.QtCore import QObject, pyqtSignal
import time

class Worker(QObject):
    progress_signal = pyqtSignal(int, int)
    status_signal = pyqtSignal(int, str)
    finished_signal = pyqtSignal(bool)
    update_signal = pyqtSignal(list)  # Сигнал теперь передает список новых файлов
    remove_signal = pyqtSignal(list)  # Для удаления по индексу

    def __init__(self, not_downloaded_files, stop_event):
        super().__init__()
        self.not_downloaded_files = not_downloaded_files
        self.stop_event = stop_event
        # Подключение сигнала к слоту
        self.update_signal.connect(self.on_update_not_downloaded_files)
        self.remove_signal.connect(self.on_remove_file)

    def on_update_not_downloaded_files(self, new_files):
        # Текущая длина списка не загруженных файлов, чтобы продолжить индексацию
        current_length = len(self.not_downloaded_files)

        # Преобразуем новые файлы в формат (индекс, данные)
        new_files_with_indices = [(current_length + i, data) for i, data in enumerate(new_files)]

        # Дополняем список не загруженных файлов новыми
        self.not_downloaded_files.extend(new_files_with_indices)

        print(self.not_downloaded_files)

    def on_remove_file(self, indices):
        for index in sorted(indices, reverse=True):
            del self.not_downloaded_files[index]

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
