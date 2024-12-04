import os
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
from requests.exceptions import ChunkedEncodingError

from mpegdash.parser import MPEGDASHParser, MPEGDASH

from kinescope.kinescope import KinescopeVideo
from kinescope.const import KINESCOPE_BASE_URL
from kinescope.exceptions import *


class VideoDownloader:
    def __init__(self, kinescope_video: KinescopeVideo,
                 temp_dir: Union[str, PathLike] = './temp',
                 ffmpeg_path: Union[str, PathLike] = 'venv/ffmpeg/bin/ffmpeg',
                 mp4decrypt_path: Union[str, PathLike] = 'venv/Bento4/bin/mp4decrypt'):
        self.kinescope_video: KinescopeVideo = kinescope_video

        self.temp_path: Path = Path(temp_dir)
        self.temp_path.mkdir(parents=True, exist_ok=True)

        self.ffmpeg_path = ffmpeg_path
        self.mp4decrypt_path = mp4decrypt_path

        self.http = Session()

        self.mpd_master: MPEGDASH = self._fetch_mpd_master()

    def __del__(self):
        rmtree(self.temp_path)

    def _merge_tracks(self, source_video_filepath: str | PathLike,
                      source_audio_filepath: str | PathLike,
                      target_filepath: str | PathLike):
        try:
            subprocess.Popen((self.ffmpeg_path,
                              "-i", source_video_filepath,
                              "-i", source_audio_filepath,
                              "-c", "copy", target_filepath,
                              "-y", "-loglevel", "error"), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             creationflags=subprocess.CREATE_NO_WINDOW).communicate()
        except FileNotFoundError:
            raise FFmpegNotFoundError('FFmpeg binary was not found at the specified path')

    def _decrypt_video(self, source_filepath: str | PathLike, target_filepath: str | PathLike, key: str):
        try:
            subprocess.Popen((self.mp4decrypt_path,
                              "--key", f"1:{key}",
                              source_filepath,
                              target_filepath), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
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

    def _fetch_segments(self, update_text_func, segments_urls: list[str], filepath: str | PathLike,
                        progress_bar_label: str = ''):
        segments_urls = [seg for i, seg in enumerate(segments_urls) if i == segments_urls.index(seg)]
        with open(filepath, 'wb') as f:
            total_segments = len(segments_urls)
            for i, segment_url in enumerate(segments_urls, 1):
                self._fetch_segment(segment_url, f)
                progress = i / total_segments
                progress_bar_length = 30
                filled_length = int(progress * progress_bar_length)
                bar = '█' * filled_length + '-' * (progress_bar_length - filled_length)
                percentage = progress * 100
                text = f"{progress_bar_label}: |{bar}| {percentage:.0f}%"
                update_text_func(text)

    def _get_segments_urls(self, resolution: tuple[int, int]) -> dict[str:list[str]]:
        try:
            return {
                adaptation_set.mime_type: [
                    segment_url.media for segment_url in adaptation_set.representations[
                        [(r.width, r.height) for r in adaptation_set.representations].index(resolution)
                        if adaptation_set.representations[0].height else 0
                    ].segment_lists[0].segment_urls
                ] for adaptation_set in self.mpd_master.periods[0].adaptation_sets
            }
        except ValueError:
            raise InvalidResolution('Invalid resolution specified')

    def _fetch_mpd_master(self) -> MPEGDASH:
        return MPEGDASHParser.parse(self.http.get(
            url=self.kinescope_video.get_mpd_master_playlist_url(),
            headers={'Referer': KINESCOPE_BASE_URL}
        ).text)

    def get_resolutions(self) -> list[tuple[int, int]]:
        for adaptation_set in self.mpd_master.periods[0].adaptation_sets:
            if adaptation_set.representations[0].height:
                return [(r.width, r.height) for r in sorted(adaptation_set.representations, key=lambda r: r.height)]

    def download(self, update_text_func, filepath, resolution, additional_info, name_video):
        if not resolution:
            resolution = self.get_resolutions()[-1]

        if additional_info != None:
            key = additional_info
            update_text_func(f"Key: {key}")
        else:
            key = self._get_license_key()
            update_text_func(f"Key: {key}")

        self._fetch_segments(update_text_func,
                             self._get_segments_urls(resolution)['video/mp4'],
                             self.temp_path / f'{self.kinescope_video.video_id}_video.mp4{".enc" if key else ""}',
                             'Video'
                             )
        self._fetch_segments(update_text_func,
                             self._get_segments_urls(resolution)['audio/mp4'],
                             self.temp_path / f'{self.kinescope_video.video_id}_audio.mp4{".enc" if key else ""}',
                             'Audio'
                             )

        if key:
            update_text_func('[*] Decrypting...')
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
            update_text_func("Done")

        filepath = Path(name_video).with_suffix('.mp4')
        filepath.parent.mkdir(parents=True, exist_ok=True)

        update_text_func('[*] Merging tracks...')
        self._merge_tracks(
            self.temp_path / f'{self.kinescope_video.video_id}_video.mp4',
            self.temp_path / f'{self.kinescope_video.video_id}_audio.mp4',
            filepath
        )
        update_text_func('Done')

        if os.path.exists(self.temp_path):
            shutil.rmtree(self.temp_path)

    def start_download(self, update_text_func, filepath, resolution, additional_info, name_video):
        if not os.path.exists(self.temp_path):
            os.makedirs(self.temp_path)

        self.download(update_text_func, filepath, resolution, additional_info, name_video)
