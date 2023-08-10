import cv2
import numpy as np
from moviepy.editor import concatenate_videoclips, VideoFileClip
import os
import asyncio
import typer
from rich.console import Console

from video_processing import VideoProcessor

DOWNLOAD_FOLDER = os.path.join(".", "downloads")

class CLI:
    def __init__(self, num_threads=24, window_size=10):
        self.num_threads = num_threads
        self.window_size = window_size

    def run(self, output_file="combined_action.mp4"):
        # Ensure the download folder exists
        if not os.path.exists(DOWNLOAD_FOLDER):
            os.makedirs(DOWNLOAD_FOLDER)
        elif not os.access(DOWNLOAD_FOLDER, os.W_OK):
            raise PermissionError(f"Cannot write to {DOWNLOAD_FOLDER}")

        analyzer = VideoProcessor(num_threads=self.num_threads, window_size=self.window_size)
        # Create an event loop and run the async function within it
        loop = asyncio.get_event_loop()
        loop.run_until_complete(analyzer.analyze_and_combine(output_file))

console = Console()
app = typer.Typer()

@app.command()
def main(
    output_file: str = "combined_action.mp4",
    num_threads: int = 24,
    window_size: int = 10,
):
    cli = CLI(num_threads=num_threads, window_size=window_size)
    cli.run(output_file)

if __name__ == "__main__":
    typer.run(main)
