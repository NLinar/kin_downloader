import os
import time
import json
import shutil
import subprocess
from io import BytesIO
from os import PathLike
from typing import Union
from pathlib import Path
from requests import Session
from subprocess import Popen
from shutil import copyfileobj, rmtree
from base64 import b64decode, b64encode
from PyQt5.QtCore import QObject, pyqtSignal
from requests.exceptions import ChunkedEncodingError
from mpegdash.parser import MPEGDASHParser, MPEGDASH
from kinescope.kinescope import KinescopeVideo
from kinescope.const import KINESCOPE_BASE_URL
from kinescope.exceptions import *

class Worker(QObject):
    progress_signal = pyqtSignal(int, int)
    status_signal = pyqtSignal(int, str)
    finished_signal = pyqtSignal(bool)
    update_signal = pyqtSignal(list)  # Сигнал теперь передает список новых файлов
    remove_signal = pyqtSignal(list)  # Для удаления по индексу

    def __init__(self, file_paths, new_file_indices, stop_event):
        super().__init__()

        # Загрузка настроек
        with open("settings.json", "r", encoding="utf-8") as file:
            settings = json.load(file)

        self.temp_path: Path = Path(settings["temp_folder"])
        self.temp_path.mkdir(parents=True, exist_ok=True)
        self.ffmpeg_path = settings["ffmpeg_path"]
        self.mp4decrypt_path = settings["4decrypt_path"]

        self.file_paths = list(enumerate(file_paths))
        self.new_file_indices = new_file_indices
        self.stop_event = stop_event
        # Подключение сигнала к слоту
        self.update_signal.connect(self.on_update_not_downloaded_files)
        self.remove_signal.connect(self.on_remove_file)

    def on_update_not_downloaded_files(self, new_files):
        # Текущая длина списка не загруженных файлов, чтобы продолжить индексацию
        current_length = len(self.file_paths)

        # Преобразуем новые файлы в формат (индекс, данные)
        new_files_with_indices = [(current_length + i, data) for i, data in enumerate(new_files)]

        # Дополняем список не загруженных файлов новыми
        self.file_paths.extend(new_files_with_indices)

        # Дополняем список не загруженных файлов индексами
        self.new_file_indices.extend([i for i, (index, file_data) in enumerate(self.file_paths) if file_data in new_files])

        print(f"on_update_new_file_indices: {self.new_file_indices}")
        print(f"on_update: {self.file_paths}")

    def on_remove_file(self, indices):
        for index in sorted(indices, reverse=True):
            del self.file_paths[index]
            del self.new_file_indices[-1]
        print(f"on_remove_new_file_indices: {self.new_file_indices}")

    def run(self):
        try:
            self.finished_signal.emit(False)
            index = 0
            while True:
                # Если все файлы обработаны, выходим из цикла
                if len(self.file_paths) == 0 or index >= len(self.file_paths):
                    print("Все файлы обработаны")
                    break
                # Проверяем статус файла в таблице, в 4-м столбце (индекс 3)
                if index not in self.new_file_indices:
                    print(f"Файл {index} уже загружен, пропускаем.")
                    index += 1
                else:
                    # Получаем текущий файл
                    entry = self.file_paths[index]
                    entry_data = entry[1]  # Извлекаем словарь из кортежа

                    # Теперь можно заполнить переменные
                    resolution = entry_data["Quality"] # надо реализовать передачу разрешений по массиву, нужен динамический
                    additional_info = entry_data["key"]
                    name_video = entry_data["Title"]

                    if self.stop_event.is_set():
                        return
                    for i in range(1, 51):
                        if self.stop_event.is_set():
                            return
                        self.progress_signal.emit(index, i * 2)
                        time.sleep(0.1)
                    if self.stop_event.is_set():
                        return
                    self.status_signal.emit(index, "Декодирование")
                    time.sleep(2)
                    if self.stop_event.is_set():
                        return
                    self.status_signal.emit(index, "Объединение")
                    time.sleep(2)
                    if self.stop_event.is_set():
                        return
                    self.status_signal.emit(index, "Загружено")
                    time.sleep(2)
                    index += 1
            self.finished_signal.emit(True)
            self.new_file_indices = []
        except Exception as e:
            print(f"Error_downloader: {e}")
