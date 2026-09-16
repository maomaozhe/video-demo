import subprocess
import tempfile
import unittest
from pathlib import Path

from video_demo.video import VideoProbeError, probe_video


class ProbeVideoTests(unittest.TestCase):
    def test_reads_metadata_from_a_real_short_video(self):
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "sample.mp4"
            subprocess.run(
                [
                    "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                    "color=c=red:s=160x90:r=10", "-t", "1", "-c:v", "mpeg4",
                    "-y", str(video),
                ],
                check=True,
                capture_output=True,
            )

            metadata = probe_video(video)

            self.assertEqual(metadata.width, 160)
            self.assertEqual(metadata.height, 90)
            self.assertEqual(metadata.duration_ms, 1000)
            self.assertEqual(metadata.fps, 10.0)
            self.assertFalse(metadata.has_audio)

    def test_missing_file_is_reported_before_ffprobe(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError):
                probe_video(Path(directory) / "missing.mp4")

    def test_corrupt_video_has_a_useful_error(self):
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "broken.mp4"
            video.write_bytes(b"not a video")

            with self.assertRaises(VideoProbeError):
                probe_video(video)


if __name__ == "__main__":
    unittest.main()
