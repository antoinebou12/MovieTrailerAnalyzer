import cv2
import numpy as np
from moviepy.editor import concatenate_videoclips, VideoFileClip
import os
import re
from yt_dlp import YoutubeDL
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

DOWNLOAD_FOLDER = os.path.join(".", "downloads")
DEFAULT_SAVE_PATH = os.path.join(".", "combined_trailer.mp4")


class VideoDownloadProcessor:
    def __init__(self, num_threads=12, window_size=10):
        self.num_threads = num_threads
        self.window_size = window_size

    def sanitize_filename(self, filename):
        """Sanitize the filename by replacing problematic characters."""
        # Remove known repeated patterns
        filename = re.sub(r'__downloads_', '', filename)

        # Replace special characters with underscores
        for char in [":", "*", "?", "<", ">", "|", '"', ' ', "\\", "/", ".", "'", "&", "(", ")", "[", "]", "{", "}", ";", "!", "@", "#", "$", "%", "^", "+", "=", ",", "~", "`", "’"]:
            filename = filename.replace(char, "_")

        # Ensure no multiple underscores
        filename = re.sub(r'_+', '_', filename)

        # Remove trailing underscores and potential file extensions
        filename = re.sub(r'_+mp4$', '.mp4', filename)

        return filename

    async def download_video(self, url, movie_name):
        """Download the video using youtube-dl and store in the specified folder."""
        # Construct a better download filename using the movie name
        sanitized_movie_name = self.sanitize_filename(movie_name)
        output_file = f"{sanitized_movie_name}_trailer.mp4"
        full_path = os.path.join(DOWNLOAD_FOLDER, output_file)

        if os.path.exists(full_path) and os.path.getsize(full_path) > 0:
            logging.info(f"Video {full_path} already exists. Skipping download.")
            return full_path

        ydl_opts = {
            "outtmpl": full_path,
            "quiet": True,  # Make youtube-dl less verbose
            "progress_hooks": [self.ydl_hook],  # Add a hook for logging
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]"
        }
        with YoutubeDL(ydl_opts) as ydl:
            try:
                info_dict = ydl.extract_info(url, download=True)
                downloaded_file_path = ydl.prepare_filename(info_dict)

                # Rename the downloaded file using the sanitized filename
                os.rename(downloaded_file_path, full_path)

                return full_path

            except Exception as e:
                logging.error(f"Error downloading video for {movie_name}: {e}")
                return None

    def ydl_hook(self, d):
        """Hook function for youtube-dl for logging purposes."""
        if d['status'] == 'finished':
            print(f"\rDownloaded {d['filename']}")
