from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
import cv2
import numpy as np
from moviepy.editor import concatenate_videoclips, VideoFileClip
import os
import asyncio
import typer
from rich.console import Console
from api import TMDBAPI

from utilities import DOWNLOAD_FOLDER, VideoDownloadProcessor, DEFAULT_SAVE_PATH

console = Console()

from rich.progress import Progress


class VideoProcessor:
    def __init__(self, num_threads=24, window_size=10):
        self.num_threads = num_threads
        self.window_size = window_size

    def calculate_variation(self, frame1, frame2):
        return np.sum(np.abs(frame1.astype(int) - frame2.astype(int)))

    def process_frame_range(
        self,
        video_path: str,
        start_frame: int,
        end_frame: int,
        fps: int,
        window_size: int,
        progress_dict: dict,  # Changed from asyncio.Task to a dictionary
    ):
        cap = cv2.VideoCapture(video_path)

        if not cap.isOpened():
            console.print(f"Failed to open video: {video_path}", style="bold red")
            return 0, 0

        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

        prev_frame = None
        max_variation = 0
        max_variation_index = start_frame
        frame_index = start_frame
        window_variation = 0
        window_frames = fps * window_size

        variations = deque(maxlen=window_frames)

        calculate_variation = self.calculate_variation

        while frame_index < end_frame and cap.isOpened():
            ret, frame = cap.read()

            if not ret:
                break

            if prev_frame is not None:
                variation = calculate_variation(prev_frame, frame)
                variations.append(variation)

                if len(variations) == window_frames:
                    window_variation -= variations[0]

                window_variation += variation

                if window_variation > max_variation:
                    max_variation = window_variation
                    max_variation_index = frame_index - window_frames + 1

            prev_frame = frame
            frame_index += 1
            progress_dict["completed"] += 1  # Use dictionary for progress tracking

        cap.release()
        return max_variation, max_variation_index

    def detect_max_variation(self, video_path: str, num_threads: int, window_size: int):
        cap = cv2.VideoCapture(video_path)

        if not cap.isOpened():
            console.print(f"Failed to open video: {video_path}", style="bold red")
            return 0, 0

        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = int(cap.get(cv2.CAP_PROP_FPS))
        frame_ranges = np.linspace(0, frame_count, num_threads + 1).astype(int)
        cap.release()

        max_variations = [0] * num_threads
        max_variation_indices = [0] * num_threads

        with Progress() as progress:
            task_ids = [progress.add_task("[cyan]Detecting maximum variation...", total=frame_count) for _ in range(num_threads)]
            progress_dicts = [{"completed": 0} for _ in range(num_threads)]
            process_frame_range = self.process_frame_range

            with ThreadPoolExecutor() as executor:
                futures = {
                    executor.submit(
                        process_frame_range,
                        video_path,
                        frame_ranges[i],
                        frame_ranges[i + 1],
                        fps,
                        window_size,
                        progress_dicts[i],
                    ): i for i in range(num_threads)
                }

                for future in as_completed(futures):
                    i = futures[future]
                    max_variations[i], max_variation_indices[i] = future.result()
                    progress.update(task_ids[i], completed=progress_dicts[i]["completed"])

        return max_variation_indices[np.argmax(max_variations)], frame_count

    def extract_10_sec_action(
        self,
        video_path: str,
        max_variation_index: int,
        output_file: str,
        window_size: int = 10,
    ):
        try:
            # Use moviepy to work with video and audio
            clip = VideoFileClip(video_path)

            start_time = max_variation_index / clip.fps
            end_time = start_time + window_size

            # Extract the subclip
            subclip = clip.subclip(start_time, end_time)

            # Write the result to a file
            subclip.write_videofile(output_file, codec="libx264")

            # Close the clips to free up memory
            subclip.close()
            clip.close()
        except Exception as e:
            console.print(
                f"Error during extraction: {str(e)}", style="bold red")

    def combine_videos(self, video_files: list, output_file: str):
        """Combine a list of videos into one video using moviepy."""
        # Check if output_file contains a directory path. If not, prepend the default path.
        if not os.path.dirname(output_file):
            output_file_path = os.path.join(DEFAULT_SAVE_PATH, output_file)
        else:
            output_file_path = output_file

        # Ensure the directory exists. If not, create it.
        os.makedirs(os.path.dirname(output_file_path), exist_ok=True)

        if video_files:
            self._combine(video_files, output_file_path)
        else:
            console.print("No videos to combine!", style="bold red")
            return

    def _combine(self, video_files, output_file_path):
        print(f"Combining {len(video_files)} videos...")

        # Use absolute paths for each video file
        video_files_absolute = [os.path.abspath(v) for v in video_files]

        clips = []
        try:
            # Load each video file using a with statement to ensure proper cleanup
            for video in video_files_absolute:
                with VideoFileClip(video) as clip:
                    clips.append(clip.copy())

            # Concatenate and write the final video
            final_clip = concatenate_videoclips(clips, method="compose")
            final_clip.write_videofile(output_file_path, codec="libx264")
        except Exception as e:
            console.print(f"Error combining videos: {e}", style="bold red")
        finally:
            # Ensure that every clip is closed properly
            for clip in clips:
                clip.close()
            if 'final_clip' in locals():
                final_clip.close()

    async def analyze_and_combine(self, output_file, movies_list=None):
        """Main workflow to analyze and combine the movie trailers."""
        tmdb_api = TMDBAPI()  # Instantiate once
        vdp = VideoDownloadProcessor()
        movie_files = []

        if not movies_list:
            movie_names = await tmdb_api.get_popular_movies()
            console.print(f"Found {len(movie_names)} popular movies.", style="bold blue")
            movies_list = [os.path.join(DOWNLOAD_FOLDER, f"{movie_name}_trailer.mp4") for movie_name in movie_names]

            console.print(f"Downloading trailers for {len(movies_list)} popular movies...", style="bold blue")
            for movie_name in movie_names:
                trailer_link = await tmdb_api.get_trailer_link(movie_name)
                if trailer_link:  # Check if we got a valid link
                    await vdp.download_video(trailer_link, movie_name)
            console.print(f"Downloaded trailers for {len(movies_list)} popular movies.", style="bold blue")
            # get all the files in DOWNLOAD_FOLDER
            movie_files = [f for f in os.listdir(DOWNLOAD_FOLDER) if f.endswith('_trailer.mp4')]
        else:
            movie_names = [os.path.basename(movie).replace('_trailer.mp4', '').replace('__', ': ') for movie in movies_list]
            movie_files = [f for f in os.listdir(DOWNLOAD_FOLDER) if f.endswith('_trailer.mp4')]

        action_clips = []

        for video_file in movie_files:
            full_video_path = os.path.join(DOWNLOAD_FOLDER, video_file)
            movie_name = os.path.basename(video_file).replace('_trailer.mp4', '')

            cap = cv2.VideoCapture(full_video_path)
            if not cap.isOpened():
                console.print(f"Failed to open video: {full_video_path}", style="bold red")
                continue
            fps = int(cap.get(cv2.CAP_PROP_FPS))
            cap.release()

            console.print(f"Extracting action sequence from {movie_name} trailer...", style="bold blue")
            console.print(f"video_file: {full_video_path}")
            action_clip_file = full_video_path.replace(".mp4", "_action.mp4")
            console.print(f"Analyzing {movie_name} trailer...", style="bold blue")

            max_variation_index, _ = self.detect_max_variation(full_video_path, self.num_threads, self.window_size)
            self.extract_10_sec_action(full_video_path, max_variation_index, action_clip_file)

            if not os.path.exists(action_clip_file):
                console.print(f"Failed to extract action sequence for {movie_name}. Skipping...", style="bold red")
                continue

            action_clips.append(action_clip_file)

        console.print("Combining all action sequences...", style="bold blue")
        self.combine_videos(action_clips, output_file)
        console.print(f"All action sequences combined into {output_file}.", style="bold blue")
        await tmdb_api.client.aclose()
