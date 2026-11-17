"""Audio analysis for the montage: waveform peaks and pauses that can be cut.

Les coupes sont calées sur les mots quand le transcript du fichier est là : une coupe
s'arrête à une marge du mot d'avant et du mot d'après, et ne mord jamais sur un mot.
À défaut, on retombe sur la marge fixe autour du blanc trouvé dans l'enveloppe.
"""
from __future__ import annotations

from array import array
import math
from pathlib import Path
import shutil
import subprocess
from typing import Any, Sequence

SAMPLE_RATE = 4000
FRAME_SECONDS = 0.02
MAX_WINDOW_SECONDS = 900

PADDING = 0.12            # ce qu'on laisse après le dernier mot avant de couper
WORD_MARGIN_BEFORE = 0.10  # et avant que le mot suivant ne commence
MIN_CUT = 0.08            # en dessous, la coupe ne gagne rien et s'entend
RESIDUAL = 0.4            # un blanc qui reste s'entend à partir de cette durée
# Un trou entre deux mots n'est un blanc que s'il est nettement plus calme que la parole :
# sinon c'est whisper qui a oublié un mot, et couper là mangerait la voix.
GAP_BELOW_SPEECH = 6.0
MIN_VOICE = 0.05          # un reste de mot plus court que ça, c'est la marque de temps qui bave
# La voix audible : la traîne d'un mot descend bien en dessous du seuil des blancs sans se taire
# pour autant. On la cherche juste au-dessus du plancher de la pièce, sur trois trames.
VOICE_ABOVE_FLOOR = 3.0
VOICE_SHARE = 0.10
QUIET_RUN = 0.06
SHOW_KEPT = 0.3           # un blanc qu'on n'a pas coupé : au-dessus, il mérite d'être cliquable


class TimelineError(ValueError):
    pass


def audio_source(project: dict[str, Any]) -> tuple[Path, float]:
    sources = project.get("sources") or []
    source = next((s for s in sources if s.get("has_audio", True)), None)
    if not source:
        raise TimelineError("Aucune source audio dans ce projet.")
    path = Path(source["path"]).expanduser()
    if not path.is_file():
        raise TimelineError("Le rush est introuvable à son emplacement d’origine.")
    return path, float(source.get("offset", 0) or 0)


def decode(path: Path, start: float, duration: float) -> array:
    """Mono 4 kHz signed 16-bit samples of [start, start + duration) in source time."""
    if duration <= 0 or duration > MAX_WINDOW_SECONDS:
        raise TimelineError("Fenêtre audio invalide.")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise TimelineError("ffmpeg est introuvable.")
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-ss", f"{max(0.0, start):.3f}", "-t", f"{duration:.3f}",
         "-i", str(path), "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "s16le", "-"],
        capture_output=True, timeout=120,
    )
    if result.returncode:
        raise TimelineError("Lecture audio impossible : " + result.stderr.decode("utf-8", "replace")[-300:])
    samples = array("h")
    samples.frombytes(result.stdout[: len(result.stdout) // 2 * 2])
    return samples


def peaks(samples: array, buckets: int) -> list[float]:
    if not samples:
        return [0.0] * buckets
    size = max(1, len(samples) // buckets)
    out = []
    for index in range(buckets):
        chunk = samples[index * size:(index + 1) * size]
        out.append(round(max((abs(v) for v in chunk), default=0) / 32768, 3))
    return out


def frame_levels(samples: array) -> list[float]:
    """Loudness per 20 ms frame, in dBFS."""
    size = int(SAMPLE_RATE * FRAME_SECONDS)
    levels = []
    for offset in range(0, len(samples) - size + 1, size):
        chunk = samples[offset:offset + size]
        rms = math.sqrt(sum(v * v for v in chunk) / size)
        levels.append(20 * math.log10(rms / 32768 + 1e-9))
    return levels


def profile(levels: Sequence[float]) -> tuple[float, float, float]:
    """Le plancher de la pièce, le niveau de la parole, et le seuil entre les deux."""
    if not levels:
        return 0.0, 0.0, 0.0
    ordered = sorted(levels)
    floor = ordered[int(len(ordered) * 0.10)]
    speech = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
    return floor, speech, floor + max(6.0, 0.30 * (speech - floor))


def quiet_spans(levels: Sequence[float], start: float, threshold: float, min_duration: float) -> list[dict[str, float]]:
    """Les passages sous un seuil donné, en temps source, à partir d'une durée."""
    found, run_start = [], None
    for index, level in enumerate(list(levels) + [0.0]):
        quiet = index < len(levels) and level < threshold
        if quiet and run_start is None:
            run_start = index
        elif not quiet and run_start is not None:
            if (index - run_start) * FRAME_SECONDS >= min_duration:
                found.append({"start": round(start + run_start * FRAME_SECONDS, 3), "end": round(start + index * FRAME_SECONDS, 3)})
            run_start = None
    return found


def silences(levels: Sequence[float], start: float, min_duration: float) -> tuple[list[dict[str, float]], float]:
    """Pauses in source time. The threshold follows the room: a noisy office has a higher floor."""
    if not levels:
        return [], 0.0
    threshold = profile(levels)[2]
    return quiet_spans(levels, start, threshold, min_duration), round(threshold, 1)


def source_words(project: dict[str, Any]) -> list[dict[str, Any]]:
    """Les mots du fichier d'origine, remis dans le temps du montage."""
    cues = project.get("source_transcript") or []
    if not isinstance(cues, list):
        return []
    offset = float(((project.get("sources") or [{}])[0] or {}).get("offset") or 0)
    out = []
    for cue in cues:
        if not isinstance(cue, dict):
            continue
        try:
            a, b = float(cue["start"]) - offset, float(cue["end"]) - offset
        except (KeyError, TypeError, ValueError):
            continue
        if not (math.isfinite(a) and math.isfinite(b)):
            continue
        b = max(b, a + 0.01)
        if b > 0:
            out.append({"start": round(max(0.0, a), 3), "end": round(b, 3), "text": str(cue.get("text", ""))})
    return sorted(out, key=lambda w: w["start"])


def merge_spans(spans: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
    out: list[list[float]] = []
    for a, b in sorted(spans):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def word_spans(words: Sequence[dict[str, Any]], before: float = WORD_MARGIN_BEFORE, after: float = PADDING) -> list[tuple[float, float]]:
    """Ce qu'une coupe n'a pas le droit de toucher : chaque mot, plus sa marge."""
    return merge_spans([(float(w["start"]) - before, float(w["end"]) + after) for w in words])


def free_pieces(span: tuple[float, float], taken: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
    """Ce qui reste de [a, b] une fois les mots et leurs marges retirés."""
    a, b = span
    pieces = []
    for ta, tb in taken:
        if tb <= a:
            continue
        if ta >= b:
            break
        if ta > a:
            pieces.append((a, ta))
        a = max(a, tb)
        if a >= b:
            break
    if a < b:
        pieces.append((a, b))
    return pieces


def refine_words(words: Sequence[dict[str, Any]], quiet: Sequence[dict[str, float]],
                 levels: Sequence[float] | None = None, start: float = 0.0,
                 loud: float | None = None) -> list[dict[str, Any]]:
    """Recale les bornes des mots sur le son.

    whisper.cpp étire souvent la fin d'un mot jusqu'au mot suivant : sur un rush de test,
    « l'erreur, » durait 1,38 s dont 0,9 s de silence. On retire donc de chaque mot les
    blancs que l'enveloppe a trouvés : ce qui reste est la voix, et c'est elle qu'on protège.
    Un mot entièrement silencieux disparaît, sauf s'il est aussi fort que la parole.
    """
    taken = merge_spans([(float(p["start"]), float(p["end"])) for p in quiet])
    out = []
    for word in words:
        a, b = float(word["start"]), float(word["end"])
        islands = [(ia, ib) for ia, ib in (free_pieces((a, b), taken) if taken else [(a, b)]) if ib - ia >= MIN_VOICE]
        if not islands:
            if levels is not None and loud is not None and _median_level(levels, start, a, b) >= loud:
                islands = [(a, b)]
            else:
                continue
        for ia, ib in islands:
            out.append({"start": round(ia, 3), "end": round(ib, 3), "text": str(word.get("text", ""))})
    return out


def voice_db(floor: float, speech: float) -> float:
    """Le seuil de la voix audible : au-dessus du plancher, mais loin sous le seuil des blancs."""
    return floor + max(VOICE_ABOVE_FLOOR, VOICE_SHARE * (speech - floor))


def voice_words(words: Sequence[dict[str, Any]], levels: Sequence[float], start: float,
                floor: float, speech: float) -> list[dict[str, Any]]:
    """Les mots ramenés à ce qu'on entend vraiment d'eux."""
    hush = quiet_spans(levels, start, voice_db(floor, speech), QUIET_RUN)
    return refine_words(words, hush, levels, start, speech - GAP_BELOW_SPEECH)


def with_kept(blanks: Sequence[dict[str, Any]], pauses: Sequence[dict[str, float]],
              segments: Sequence[dict[str, float]], floor: float = SHOW_KEPT) -> list[dict[str, Any]]:
    """Ajoute les blancs que l'algorithme n'a pas osé couper : un clic suffira à les couper."""
    cuts = [(float(b["start"]), float(b["end"])) for b in blanks]
    out = [dict(b) for b in blanks]
    for pause in pauses:
        for piece_start, piece_end in free_pieces((float(pause["start"]), float(pause["end"])), cuts):
            for segment in segments:
                lo, hi = max(piece_start, segment["start"]), min(piece_end, segment["end"])
                if hi - lo >= floor:
                    out.append({"start": round(lo, 3), "end": round(hi, 3), "cut": False})
    return sorted(out, key=lambda b: b["start"])


def word_pauses(words: Sequence[dict[str, Any]], min_duration: float,
                levels: Sequence[float] | None = None, start: float = 0.0, loud: float | None = None) -> list[dict[str, float]]:
    """Les blancs entre deux mots : respirations et bruit de fond, que l'enveloppe rate."""
    out = []
    ordered = sorted(words, key=lambda w: float(w["start"]))
    for first, second in zip(ordered, ordered[1:]):
        a, b = float(first["end"]), float(second["start"])
        if b - a < min_duration:
            continue
        if levels is not None and loud is not None and _median_level(levels, start, a, b) >= loud:
            continue
        out.append({"start": round(a, 3), "end": round(b, 3)})
    return out


def _median_level(levels: Sequence[float], start: float, a: float, b: float) -> float:
    lo = max(0, int((a - start) / FRAME_SECONDS))
    hi = min(len(levels), int((b - start) / FRAME_SECONDS) + 1)
    window = sorted(levels[lo:hi])
    return window[len(window) // 2] if window else -120.0


def plan_blanks(segments: Sequence[dict[str, float]], pauses: Sequence[dict[str, float]],
                words: Sequence[dict[str, Any]] | None = None, padding: float = PADDING,
                min_cut: float = MIN_CUT) -> list[dict[str, Any]]:
    """Les coupes à faire : le centre de chaque blanc, sans jamais mordre sur un mot."""
    taken = word_spans(words, WORD_MARGIN_BEFORE, padding) if words else []
    found = []
    for pause in pauses:
        a, b = float(pause["start"]), float(pause["end"])
        pieces = free_pieces((a, b), taken) if taken else [(a + padding, b - padding)]
        for piece_start, piece_end in pieces:
            for segment in segments:
                lo, hi = max(piece_start, segment["start"]), min(piece_end, segment["end"])
                if hi - lo >= min_cut:
                    found.append((round(lo, 3), round(hi, 3)))
    return [{"start": a, "end": b, "cut": True} for a, b in merge_spans(found)]


def cut_blanks(segments: Sequence[dict[str, float]], blanks: Sequence[dict[str, Any]], min_piece: float = 0.15) -> list[dict[str, float]]:
    """Les morceaux gardés : les segments moins les blancs marqués à couper."""
    result = []
    for segment in segments:
        pieces = [(segment["start"], segment["end"])]
        for blank in blanks:
            if not blank.get("cut", True):
                continue
            cut_start, cut_end = float(blank["start"]), float(blank["end"])
            if cut_end - cut_start <= 0:
                continue
            next_pieces = []
            for a, b in pieces:
                if cut_end <= a or cut_start >= b:
                    next_pieces.append((a, b))
                    continue
                if cut_start > a:
                    next_pieces.append((a, cut_start))
                if cut_end < b:
                    next_pieces.append((cut_end, b))
            pieces = next_pieces
        result.extend({"start": round(a, 3), "end": round(b, 3)} for a, b in pieces if b - a >= min_piece)
    return result


def cut_silences(segments: Sequence[dict[str, float]], pauses: Sequence[dict[str, float]], padding: float = PADDING,
                 min_piece: float = 0.15, words: Sequence[dict[str, Any]] | None = None) -> list[dict[str, float]]:
    """Remove the inside of each pause from the segments, keeping a breath on both sides of every word."""
    return cut_blanks(segments, plan_blanks(segments, pauses, words, padding), min_piece)


def residual_blanks(pauses: Sequence[dict[str, float]], segments: Sequence[dict[str, float]], floor: float = RESIDUAL) -> list[dict[str, float]]:
    """Les blancs qui restent dans les morceaux gardés : ce qu'on entendrait encore."""
    out = []
    for pause in pauses:
        for segment in segments:
            lo, hi = max(float(pause["start"]), segment["start"]), min(float(pause["end"]), segment["end"])
            if hi - lo > floor:
                out.append({"start": round(lo, 3), "end": round(hi, 3)})
    return out


def bites(blanks: Sequence[dict[str, Any]], words: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Les coupes qui mordent sur un mot. Doit toujours être vide."""
    out = []
    for blank in blanks:
        if not blank.get("cut", True):
            continue
        for word in words:
            if float(blank["start"]) < float(word["end"]) - 0.001 and float(blank["end"]) > float(word["start"]) + 0.001:
                out.append({"blank": dict(blank), "word": dict(word)})
                break
    return out


def analyse_montage(project: dict[str, Any], segments: Sequence[dict[str, float]], min_duration: float = 0.35) -> dict[str, Any]:
    if not segments:
        raise TimelineError("Le passage ne contient aucun segment.")
    path, offset = audio_source(project)
    start, end = min(s["start"] for s in segments), max(s["end"] for s in segments)
    samples = decode(path, start + offset, end - start)
    levels = frame_levels(samples)
    floor, speech, threshold = profile(levels)
    pauses = quiet_spans(levels, start, threshold, min_duration)
    words = [w for w in source_words(project) if w["end"] > start and w["start"] < end]
    words = voice_words(words, levels, start, floor, speech)
    gaps = word_pauses(words, min_duration, levels, start, speech - GAP_BELOW_SPEECH)
    found = [{"start": a, "end": b} for a, b in merge_spans([(p["start"], p["end"]) for p in pauses + gaps])]
    inside = [p for p in found if any(p["start"] < s["end"] and p["end"] > s["start"] for s in segments)]
    blanks = with_kept(plan_blanks(segments, inside, words), inside, segments)
    trimmed = cut_blanks(segments, blanks)
    before = sum(s["end"] - s["start"] for s in segments)
    after = sum(s["end"] - s["start"] for s in trimmed)
    return {"segments": trimmed, "silences": inside, "blanks": blanks,
            "count": sum(1 for b in blanks if b.get("cut", True)),
            "words": [[w["start"], w["end"]] for w in words], "word_based": bool(words),
            "residual": residual_blanks(inside, trimmed),
            "saved_seconds": round(before - after, 2), "threshold_db": round(threshold, 1),
            "voice_db": round(voice_db(floor, speech), 1)}


def waveform(project: dict[str, Any], start: float, end: float, buckets: int = 600) -> dict[str, Any]:
    if end <= start:
        raise TimelineError("Fenêtre invalide.")
    path, offset = audio_source(project)
    buckets = max(50, min(2000, int(buckets)))
    samples = decode(path, max(0.0, start) + offset, end - max(0.0, start))
    levels = frame_levels(samples)
    floor, speech, _ = profile(levels)
    words = [w for w in source_words(project) if w["end"] > start and w["start"] < end]
    words = voice_words(words, levels, max(0.0, start), floor, speech)
    return {"start": max(0.0, start), "end": end, "peaks": peaks(samples, buckets),
            "words": [[w["start"], w["end"]] for w in words]}
