import os
import time
import json
import shutil
import subprocess
from io import BytesIO
from os import PathLike
from typing import Optional
from pathlib import Path
from requests import Session
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
    update_signal = pyqtSignal(list)  # Сигнал передает список новых файлов
    update_resolution_signal = pyqtSignal(list)  # Сигнал передает список качеств
    remove_signal = pyqtSignal(list)  # Для удаления по индексу

    def __init__(self, file_paths, resolution_files, new_file_indices, stop_event):
        super().__init__()

        # Загрузка настроек
        with open("settings.json", "r", encoding="utf-8") as file:
            settings = json.load(file)

        self.kinescope_video: Optional[KinescopeVideo] = None
        self.mpd_master: Optional[MPEGDASH] = None
        self.temp_path: Path = Path(settings["temp_folder"])
        self.temp_path.mkdir(parents=True, exist_ok=True)
        self.ffmpeg_path = settings["ffmpeg_path"]
        self.mp4decrypt_path = settings["4decrypt_path"]
        self.output_dir: Path = Path(settings["save_folder"])
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.http = Session()

        self.file_paths = list(enumerate(file_paths))
        self.resolution_files = list(resolution_files)
        self.new_file_indices = new_file_indices
        self.stop_event = stop_event
        # Подключение сигнала к слоту
        self.update_signal.connect(self.on_update_not_downloaded_files)
        self.update_resolution_signal.connect(self.on_update_resolution)
        self.remove_signal.connect(self.on_remove_file)

    def on_update_not_downloaded_files(self, new_files):
        # Текущая длина списка не загруженных файлов, чтобы продолжить индексацию
        current_length = len(self.file_paths)

        # Преобразуем новые файлы в формат (индекс, данные)
        new_files_with_indices = [(current_length + i, data) for i, data in enumerate(new_files)]

        # Дополняем список не загруженных файлов новыми
        self.file_paths.extend(new_files_with_indices)

        # Дополняем список не загруженных файлов индексами
        self.new_file_indices.extend(
            [i for i, (index, file_data) in enumerate(self.file_paths) if file_data in new_files])

        # print(f"on_update_new_file_indices: {self.new_file_indices}")
        # print(f"on_update: {self.file_paths}")

    def on_update_resolution(self, new_resolution_files):
        self.resolution_files = list(new_resolution_files)
        # print(f"Данные в downloader: {new_resolution_files}")

    def on_remove_file(self, indices):
        for index in sorted(indices, reverse=True):
            del self.file_paths[index]
            del self.resolution_files[index]
            del self.new_file_indices[-1]
        # print(f"on_remove_new_file_indices: {self.new_file_indices}")

    # ======================================================================================================================
    def _merge_tracks(self, source_video_filepath: str | PathLike,
                      source_audio_filepath: str | PathLike,
                      target_filepath: str | PathLike):
        try:
            subprocess.Popen((str(self.ffmpeg_path),
                              "-i", str(source_video_filepath),
                              "-i", str(source_audio_filepath),
                              "-c", "copy", str(target_filepath),
                              "-y", "-loglevel", "error"), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             creationflags=subprocess.CREATE_NO_WINDOW).communicate()
        except FileNotFoundError:
            raise FFmpegNotFoundError('FFmpeg binary was not found at the specified path')

    def _decrypt_video(self, source_filepath: str | PathLike, target_filepath: str | PathLike, key: str):
        try:
            subprocess.Popen((str(self.mp4decrypt_path),
                              "--key", f"1:{key}",
                              str(source_filepath),
                              str(target_filepath)), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             creationflags=subprocess.CREATE_NO_WINDOW).communicate()
        except FileNotFoundError:
            raise FFmpegNotFoundError('mp4decrypt binary was not found at the specified path')

    def _get_license_key(self) -> str:
        return b64decode(
            self.http.post(
                url=self.kinescope_video.get_clearkey_license_url(),
                headers={'origin': KINESCOPE_BASE_URL},
                json={
                    'kids': [
                        b64encode(bytes.fromhex(
                            self.mpd_master
                            .periods[0]
                            .adaptation_sets[0]
                            .content_protections[0]
                            .cenc_default_kid.replace('-', '')
                        )).decode().replace('=', '')
                    ],
                    'type': 'temporary'
                }
            ).json()['keys'][0]['k'] + '=='
        ).hex() if self.mpd_master.periods[0].adaptation_sets[0].content_protections else None

    def _fetch_segment(self, segment_url: str, file):
        for _ in range(5):
            try:
                copyfileobj(
                    BytesIO(self.http.get(segment_url, stream=True).content),
                    file
                )
                return
            except ChunkedEncodingError:
                pass

        raise SegmentDownloadError(f'Failed to download segment {segment_url}')

    def _fetch_segments(self, index, segments_urls, filepath: str | PathLike, total_segments_count, offset):
        with open(filepath, 'wb') as f:
            for i, segment_url in enumerate(segments_urls, 1):
                if self.stop_event.is_set():
                    return

                # Загружаем сегмент
                self._fetch_segment(segment_url, f)

                # Отправляем сигнал с общим процентом выполнения
                offset = offset + 1
                progress = int((offset / total_segments_count) * 100)
                # print(f"progress: {progress}")
                self.progress_signal.emit(index, progress)

    def get_segments_count(self, resolution: tuple[int, int]) -> dict[str, list[str]]:
        # Получаем список сегментов для видео и аудио
        segments_urls = self._get_segments_urls(resolution)

        # Убираем дубликаты сегментов по каждому типу
        video_segments = [seg for i, seg in enumerate(segments_urls.get("video/mp4", [])) if
                          i == segments_urls["video/mp4"].index(seg)]
        audio_segments = [seg for i, seg in enumerate(segments_urls.get("audio/mp4", [])) if
                          i == segments_urls["audio/mp4"].index(seg)]

        # Возвращаем сами сегменты, а не их количество
        return {"video": video_segments, "audio": audio_segments}

    def _get_segments_urls(self, resolution: tuple[int, int]) -> dict[str:list[str]]:
        try:
            result = {}
            for adaptation_set in self.mpd_master.periods[0].adaptation_sets:
                resolutions = [(r.width, r.height) for r in adaptation_set.representations]
                idx = resolutions.index(resolution) if adaptation_set.representations[0].height else 0
                representation = adaptation_set.representations[idx]
                base_url = representation.base_urls[0].base_url_value
                result[adaptation_set.mime_type] = [
                    base_url + (segment_url.media or '')
                    for segment_url in representation.segment_lists[0].segment_urls]

            return result
        except ValueError:
            raise InvalidResolution('Invalid resolution specified')

    def _fetch_mpd_master(self) -> MPEGDASH:
        mpd_text = self.http.get(
            url=self.kinescope_video.get_mpd_master_playlist_url(),
            headers={'Referer': KINESCOPE_BASE_URL}
        ).text
        # Замена "https://dashif.org/"minBufferTime на "https://dashif.org/" minBufferTime
        mpd_text = mpd_text.replace('"https://dashif.org/"minBufferTime', '"https://dashif.org/" minBufferTime')

        return MPEGDASHParser.parse(mpd_text)

    # ======================================================================================================================

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
                    resolution = self.resolution_files[index]
                    additional_info = entry_data["key"]
                    name_video = entry_data["Title"]
                    input_url = "https://kinescope.io/" + entry_data["Video ID"]
                    referer = entry_data["Referer"]
                    print(f"Качество: {resolution}")
                    print(f"Название: {name_video}")
                    print(f"URL: {input_url}")
                    print(f"Referer: {referer}")

                    self.progress_signal.emit(index, 0)

                    self.kinescope_video = KinescopeVideo(url=input_url, video_id=entry_data["Video ID"], referer_url=referer)
                    self.mpd_master = self._fetch_mpd_master()  # надо сделать проверку на то что mpd не удален в kinescope

                    if additional_info:
                        key = additional_info
                    else:
                        key = self._get_license_key()

                    print(f"Ключ: {key}")

                    # Список сегментов
                    segment_counts = self.get_segments_count(resolution)

                    # Общее количество сегментов
                    total_segments_count = len(segment_counts['video']) + len(segment_counts['audio'])

                    if self.stop_event.is_set():
                        return
                    # Скачивание видео
                    self._fetch_segments(index,
                                         segment_counts['video'],
                                         self.temp_path / f'{self.kinescope_video.video_id}_video.mp4{".enc" if key else ""}',
                                         total_segments_count,
                                         offset=0
                                         )
                    if self.stop_event.is_set():
                        return
                    # Скачивание аудио
                    self._fetch_segments(index,
                                         segment_counts['audio'],
                                         self.temp_path / f'{self.kinescope_video.video_id}_audio.mp4{".enc" if key else ""}',
                                         total_segments_count,
                                         offset=len(segment_counts['video'])
                                         )
                    if self.stop_event.is_set():
                        return
                    if key:
                        print("Декодирование")
                        self.status_signal.emit(index, "Декодирование")
                        self._decrypt_video(
                            self.temp_path / f'{self.kinescope_video.video_id}_video.mp4.enc',
                            self.temp_path / f'{self.kinescope_video.video_id}_video.mp4',
                            key
                        )
                        self._decrypt_video(
                            self.temp_path / f'{self.kinescope_video.video_id}_audio.mp4.enc',
                            self.temp_path / f'{self.kinescope_video.video_id}_audio.mp4',
                            key
                        )
                    if self.stop_event.is_set():
                        return
                    self.status_signal.emit(index, "Объединение")
                    filepath = self.output_dir / Path(name_video).with_suffix('.mp4').name
                    filepath.parent.mkdir(parents=True, exist_ok=True)

                    self._merge_tracks(
                        self.temp_path / f'{self.kinescope_video.video_id}_video.mp4',
                        self.temp_path / f'{self.kinescope_video.video_id}_audio.mp4',
                        filepath
                    )

                    # Удаляем содержимое папки
                    shutil.rmtree(self.temp_path, ignore_errors=True)
                    # Создаём папку заново, чтобы сама папка осталась
                    os.makedirs(self.temp_path, exist_ok=True)

                    if self.stop_event.is_set():
                        return
                    self.status_signal.emit(index, "Загружено")
                    time.sleep(2)
                    index += 1
            self.finished_signal.emit(True)
            self.new_file_indices = []
        except Exception as e:
            print(f"Error_downloader: {e}")
