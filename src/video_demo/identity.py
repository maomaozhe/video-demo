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


def prioritize_reviews(result: IdentityResult, scene_by_track: dict[str, int],
                       *, per_category: int = 3) -> list[ReviewCandidate]:
    """Keep the strongest cross-scene and local-fragment candidates separately."""
    if per_category <= 0:
        raise ValueError("per-category limit must be positive")
    scenes_by_person: dict[str, set[int]] = {}
    for track_id, person_id in result.track_to_person.items():
        scenes_by_person.setdefault(person_id, set()).add(scene_by_track[track_id])
    selected = []
    counts: dict[tuple[str, str], int] = {}
    for item in sorted(result.review_candidates, key=lambda x: -x.similarity):
        kind = ("same_scene" if scene_by_track[item.track_id] in
                scenes_by_person[item.possible_person_id] else "cross_scene")
        key = item.track_id, kind
        if counts.get(key, 0) < per_category:
            selected.append(item)
            counts[key] = counts.get(key, 0) + 1
    return selected


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return sum(a * b for a, b in zip(left, right)) / (
        math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    )


def associate_tracklets(
    tracklets: list[Tracklet], *, merge_threshold: float, review_threshold: float,
    ambiguity_margin: float = 0.05, max_review_candidates: int = 3,
    merge_enabled: bool = True,
) -> IdentityResult:
    """Associate precomputed tracklets; thresholds must be calibrated on local samples."""
    if not 0 <= review_threshold < merge_threshold <= 1:
        raise ValueError("invalid similarity thresholds")
    if not 0 <= ambiguity_margin <= 1:
        raise ValueError("invalid ambiguity margin")
    if max_review_candidates <= 0:
        raise ValueError("max review candidates must be positive")
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

        if merge_enabled and candidates and candidates[0][0] >= merge_threshold and (
            len(candidates) == 1 or candidates[0][0] - candidates[1][0] >= ambiguity_margin
        ):
            person_id = candidates[0][1]
            groups[person_id].append(track)
        else:
            person_id = f"P{len(groups) + 1}"
            groups[person_id] = [track]
            for similarity, possible_person_id in candidates[:max_review_candidates]:
                if similarity >= review_threshold:
                    review.append(ReviewCandidate(track.track_id, possible_person_id, similarity))
        mapping[track.track_id] = person_id

    return IdentityResult(mapping, review)
