import json
import tempfile
import threading
import unittest
from contextlib import contextmanager
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

from video_demo.web import make_server
from test_result_store import make_run


_open_local = build_opener(ProxyHandler({})).open


@contextmanager
def running_server(runs_dir: Path):
    server = make_server(runs_dir, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class WebTests(unittest.TestCase):
    def test_lists_runs_and_returns_detail(self):
        with tempfile.TemporaryDirectory() as temporary:
            make_run(Path(temporary), "sample-full", "a" * 64)
            with running_server(Path(temporary)) as (server, base):
                self.assertEqual(server.server_address[0], "127.0.0.1")
                with _open_local(base + "/api/videos") as response:
                    videos = json.load(response)
                with _open_local(base + "/api/runs/sample-full") as response:
                    detail = json.load(response)

            self.assertEqual(videos[0]["preferred_run_id"], "sample-full")
            self.assertEqual(detail["result"]["events"][0]["action"], "搭建积木")
            self.assertIn("搭建积木", detail["summary"])

    def test_downloads_only_known_files_and_referenced_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = make_run(Path(temporary), "sample-full", "a" * 64)
            (directory / "evidence" / "secret.jpg").write_bytes(b"secret")
            with running_server(Path(temporary)) as (_, base):
                with _open_local(base + "/api/runs/sample-full/files/summary.md") as response:
                    self.assertEqual(response.headers.get_content_type(), "text/markdown")
                    self.assertIn("搭建积木", response.read().decode())
                with _open_local(base + "/api/runs/sample-full/evidence/F1.jpg") as response:
                    self.assertEqual(response.headers.get_content_type(), "image/jpeg")
                    self.assertEqual(response.read(), b"jpeg bytes")
                for route in [
                    "/api/runs/sample-full/evidence/secret.jpg",
                    "/api/runs/%2e%2e/files/manifest.json",
                    "/api/runs/sample-full/files/secrets.txt",
                ]:
                    with self.subTest(route=route), self.assertRaises(HTTPError) as raised:
                        _open_local(base + route)
                    self.assertEqual(raised.exception.code, 404)

    def test_serves_page_and_rejects_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            with running_server(Path(temporary)) as (_, base):
                with _open_local(base + "/") as response:
                    self.assertEqual(response.headers.get_content_type(), "text/html")
                    self.assertIn("视频结果", response.read().decode())
                with _open_local(base + "/app.js") as response:
                    self.assertEqual(response.headers.get_content_type(), "text/javascript")
                with self.assertRaises(HTTPError) as raised:
                    _open_local(Request(base + "/api/videos", data=b"{}", method="POST"))
                self.assertEqual(raised.exception.code, 405)


if __name__ == "__main__":
    unittest.main()
