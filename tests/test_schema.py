import unittest

from video_demo.schema import Event, Evidence, validate_event


class EventValidationTests(unittest.TestCase):
    def test_accepts_event_with_evidence_inside_video_and_event(self):
        event = Event(
            start_ms=1000,
            end_ms=3000,
            person_id="P1",
            action="拿起工具",
            status="观察到",
            evidence=[Evidence(timestamp_ms=1500, frame_id="F15")],
        )

        validate_event(event, duration_ms=5000)

    def test_rejects_event_outside_video(self):
        event = Event(start_ms=1000, end_ms=6000, action="检查设备")

        with self.assertRaisesRegex(ValueError, "video duration"):
            validate_event(event, duration_ms=5000)

    def test_rejects_evidence_outside_event(self):
        event = Event(
            start_ms=1000,
            end_ms=3000,
            action="检查设备",
            evidence=[Evidence(timestamp_ms=4000, frame_id="F40")],
        )

        with self.assertRaisesRegex(ValueError, "evidence"):
            validate_event(event, duration_ms=5000)

    def test_completed_action_requires_evidence(self):
        event = Event(start_ms=1000, end_ms=3000, action="安装零件", status="已完成")

        with self.assertRaisesRegex(ValueError, "completed"):
            validate_event(event, duration_ms=5000)


if __name__ == "__main__":
    unittest.main()
