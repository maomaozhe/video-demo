import unittest

from video_demo.identity import Tracklet, associate_tracklets


class IdentityTests(unittest.TestCase):
    def test_nonoverlapping_matching_tracklets_share_person_id(self):
        tracks = [
            Tracklet("T1", 0, 1000, (1.0, 0.0)),
            Tracklet("T2", 3000, 4000, (0.99, 0.01)),
        ]

        result = associate_tracklets(tracks, merge_threshold=0.9, review_threshold=0.7)

        self.assertEqual(result.track_to_person, {"T1": "P1", "T2": "P1"})
        self.assertEqual(result.review_candidates, [])

    def test_simultaneously_visible_people_are_never_merged(self):
        tracks = [
            Tracklet("T1", 0, 2000, (1.0, 0.0)),
            Tracklet("T2", 1000, 3000, (1.0, 0.0)),
        ]

        result = associate_tracklets(tracks, merge_threshold=0.9, review_threshold=0.7)

        self.assertEqual(result.track_to_person, {"T1": "P1", "T2": "P2"})

    def test_borderline_similarity_requests_review_without_merging(self):
        tracks = [
            Tracklet("T1", 0, 1000, (1.0, 0.0)),
            Tracklet("T2", 3000, 4000, (0.8, 0.6)),
        ]

        result = associate_tracklets(tracks, merge_threshold=0.9, review_threshold=0.7)

        self.assertEqual(result.track_to_person, {"T1": "P1", "T2": "P2"})
        self.assertEqual(result.review_candidates[0].track_id, "T2")
        self.assertEqual(result.review_candidates[0].possible_person_id, "P1")

    def test_rejects_duplicate_track_ids(self):
        tracks = [
            Tracklet("T1", 0, 1000, (1.0, 0.0)),
            Tracklet("T1", 3000, 4000, (1.0, 0.0)),
        ]

        with self.assertRaisesRegex(ValueError, "duplicate"):
            associate_tracklets(tracks, merge_threshold=0.9, review_threshold=0.7)

    def test_two_equally_good_people_remain_separate_and_need_review(self):
        tracks = [
            Tracklet("T1", 0, 1000, (1.0, 0.0)),
            Tracklet("T2", 0, 1000, (1.0, 0.0)),
            Tracklet("T3", 3000, 4000, (1.0, 0.0)),
        ]

        result = associate_tracklets(tracks, merge_threshold=0.9, review_threshold=0.7)

        self.assertEqual(result.track_to_person["T3"], "P3")
        self.assertEqual({candidate.possible_person_id for candidate in result.review_candidates}, {"P1", "P2"})


if __name__ == "__main__":
    unittest.main()
