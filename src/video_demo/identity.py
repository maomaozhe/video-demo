"""Conservative within-video tracklet association using appearance embeddings."""

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Tracklet:
    track_id: str
    start_ms: int
    end_ms: int
    embedding: tuple[float, ...]


@dataclass(frozen=True)
class ReviewCandidate:
    track_id: str
    possible_person_id: str
    similarity: float


@dataclass(frozen=True)
class IdentityResult:
    track_to_person: dict[str, str]
    review_candidates: list[ReviewCandidate]


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return sum(a * b for a, b in zip(left, right)) / (
        math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    )


def associate_tracklets(
    tracklets: list[Tracklet], *, merge_threshold: float, review_threshold: float,
    ambiguity_margin: float = 0.05,
) -> IdentityResult:
    """Associate precomputed tracklets; thresholds must be calibrated on local samples."""
    if not 0 <= review_threshold < merge_threshold <= 1:
        raise ValueError("invalid similarity thresholds")
    if not 0 <= ambiguity_margin <= 1:
        raise ValueError("invalid ambiguity margin")
    if not tracklets:
        return IdentityResult({}, [])

    dimensions = len(tracklets[0].embedding)
    seen_ids = set()
    for track in tracklets:
        if track.track_id in seen_ids:
            raise ValueError(f"duplicate track ID: {track.track_id}")
        seen_ids.add(track.track_id)
        if track.start_ms < 0 or track.end_ms <= track.start_ms:
            raise ValueError(f"invalid time range for {track.track_id}")
        if len(track.embedding) != dimensions or dimensions == 0:
            raise ValueError("inconsistent embedding dimensions")
        if not all(math.isfinite(value) for value in track.embedding) or not any(track.embedding):
            raise ValueError(f"invalid embedding for {track.track_id}")

    mapping: dict[str, str] = {}
    review: list[ReviewCandidate] = []
    groups: dict[str, list[Tracklet]] = {}
    for track in sorted(tracklets, key=lambda item: (item.start_ms, item.end_ms, item.track_id)):
        candidates = []
        for person_id, members in groups.items():
            if any(track.start_ms < member.end_ms and member.start_ms < track.end_ms for member in members):
                continue
            similarity = max(_cosine(track.embedding, member.embedding) for member in members)
            candidates.append((similarity, person_id))
        candidates.sort(reverse=True)

        if candidates and candidates[0][0] >= merge_threshold and (
            len(candidates) == 1 or candidates[0][0] - candidates[1][0] >= ambiguity_margin
        ):
            person_id = candidates[0][1]
            groups[person_id].append(track)
        else:
            person_id = f"P{len(groups) + 1}"
            groups[person_id] = [track]
            for similarity, possible_person_id in candidates:
                if similarity >= review_threshold:
                    review.append(ReviewCandidate(track.track_id, possible_person_id, similarity))
        mapping[track.track_id] = person_id

    return IdentityResult(mapping, review)
