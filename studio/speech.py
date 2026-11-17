"""Local word-by-word transcription with whisper.cpp. Nothing leaves this machine."""

from __future__ import annotations

from . import proc
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import unicodedata
import uuid
from typing import Any, Callable, Iterable, Sequence

DEFAULT_WHISPER_MODEL = Path.home() / ".cache/whisper-cpp/ggml-large-v3-turbo.bin"
TRANSCRIBE_CHUNK_SECONDS = 30 * 60
TRANSCRIBE_OVERLAP_SECONDS = 4.0

_ID_NAMESPACE = uuid.UUID("3d2a1b54-0bdb-4c66-b2c3-b794585088f0")
_TIME_RE = re.compile(
    r"^\s*(?:(?P<h>\d{1,3}):)?(?P<m>\d{2}):(?P<s>\d{2})"
    r"(?P<f>[,.]\d{1,3})?\s*$"
)
_TIMING_LINE_RE = re.compile(r"^\s*(\S+)\s*-->\s*(\S+)(?:\s+.*)?$")

Progress = Callable[[float, str], None]
Check = Callable[[], None]


class SpeechError(RuntimeError):
    """A user-facing transcription error."""


SelectionError = SpeechError  # the message wording in the extracted helpers below


def _noop_progress(percent: float, message: str) -> None:
    del percent, message


def _noop_check() -> None:
    return None


def _cue_id(start: float, end: float, text: str, ordinal: int) -> str:
    raw = f"{start:.3f}|{end:.3f}|{ordinal}|{text}"
    return str(uuid.uuid5(_ID_NAMESPACE, raw))



def _parse_timestamp(value: str) -> float:
    match = _TIME_RE.match(value)
    if not match:
        raise SelectionError(f"Horodatage invalide : {value!r}")
    hours = int(match.group("h") or 0)
    minutes = int(match.group("m"))
    seconds = int(match.group("s"))
    if minutes >= 60 or seconds >= 60:
        raise SelectionError(f"Horodatage invalide : {value!r}")
    fraction = match.group("f")
    millis = float("0." + fraction[1:]) if fraction else 0.0
    return hours * 3600 + minutes * 60 + seconds + millis


def _number(value: Any, field: str, index: int) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SelectionError(f"JSON : {field} doit être un nombre au segment {index + 1}.")
    result = float(value)
    if not math.isfinite(result):
        raise SelectionError(f"JSON : {field} doit être fini au segment {index + 1}.")
    return result


def _validated_cues(items: Iterable[dict[str, Any]], *, preserve_ids: bool) -> list[dict[str, Any]]:
    cues: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise SelectionError(f"JSON : le segment {index + 1} doit être un objet.")
        if "start" not in item or "end" not in item or "text" not in item:
            raise SelectionError(
                f"JSON : le segment {index + 1} doit contenir start, end et text."
            )
        start = _number(item["start"], "start", index)
        end = _number(item["end"], "end", index)
        text = item["text"]
        if not isinstance(text, str) or not text.strip():
            raise SelectionError(f"JSON : texte vide ou invalide au segment {index + 1}.")
        if start < 0 or end <= start:
            raise SelectionError(
                f"JSON : intervalle invalide au segment {index + 1} ({start:g}–{end:g})."
            )
        supplied = item.get("id") if preserve_ids else None
        cue_id = supplied.strip() if isinstance(supplied, str) and supplied.strip() else _cue_id(
            start, end, text.strip(), index
        )
        if cue_id in seen_ids:
            raise SelectionError(f"JSON : identifiant de transcript dupliqué : {cue_id}")
        seen_ids.add(cue_id)
        cues.append({"id": cue_id, "start": round(start, 3), "end": round(end, 3), "text": text.strip()})

    cues.sort(key=lambda cue: (cue["start"], cue["end"], cue["id"]))
    return cues



def _parse_subtitles(text: str, *, words: bool = False) -> list[dict[str, Any]]:
    # Normalize separators only. Caption wording and punctuation remain intact.
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    lines = normalized.split("\n")
    cues: list[dict[str, Any]] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or line == "WEBVTT" or line.startswith("X-TIMESTAMP-MAP"):
            i += 1
            continue
        if line.startswith(("NOTE", "STYLE", "REGION")):
            i += 1
            while i < len(lines) and lines[i].strip():
                i += 1
            continue
        timing_index = i
        if "-->" not in line and i + 1 < len(lines) and "-->" in lines[i + 1]:
            timing_index = i + 1  # optional SRT number or VTT cue identifier
        timing = _TIMING_LINE_RE.match(lines[timing_index])
        if not timing:
            raise SelectionError(
                f"Sous-titres invalides près de la ligne {i + 1} : ligne de temps attendue."
            )
        start = _parse_timestamp(timing.group(1))
        end = _parse_timestamp(timing.group(2))
        if end < start:
            raise SelectionError(f"Sous-titres : fin antérieure au début près de la ligne {timing_index + 1}.")
        i = timing_index + 1
        payload: list[str] = []
        while i < len(lines) and lines[i].strip():
            payload.append(lines[i].strip())
            i += 1
        cue_text = " ".join(payload).strip()
        if not cue_text:
            # whisper.cpp opens word-level output (-ml 1 -sow) with an empty cue: it holds no word, so nothing is lost.
            continue
        cues.append({"start": start, "end": end, "text": cue_text})
    if words:
        # Word-level output keeps its zero-length words: grouping decides where they belong.
        if not cues:
            raise SelectionError("Aucun segment horodaté trouvé dans les sous-titres.")
        return sorted(cues, key=lambda cue: (cue["start"], cue["end"]))
    cues = _absorb_instant_cues(cues)
    if not cues:
        raise SelectionError("Aucun segment horodaté trouvé dans les sous-titres.")
    return _validated_cues(cues, preserve_ids=False)


def _absorb_instant_cues(cues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach zero-length cues to their neighbour instead of rejecting the whole file.

    whisper.cpp regularly emits a lone word with identical start and end when a
    line reaches its length limit. The word belongs to the sentence around it, so
    it joins the previous cue (or the next one at the very start) and no text is lost.
    """
    kept: list[dict[str, Any]] = []
    leading: list[dict[str, Any]] = []
    for cue in cues:
        if cue["end"] > cue["start"]:
            if leading:
                cue = {**cue, "start": min(item["start"] for item in leading + [cue]), "text": " ".join([*(item["text"] for item in leading), cue["text"]])}
                leading = []
            kept.append(cue)
        elif kept:
            kept[-1] = {**kept[-1], "end": max(kept[-1]["end"], cue["end"]), "text": f"{kept[-1]['text']} {cue['text']}"}
        else:
            leading.append(cue)
    if leading and kept:
        kept[0] = {**kept[0], "text": " ".join([*(item["text"] for item in leading), kept[0]["text"]])}
    return kept


def parse_transcript(text: str) -> list[dict[str, Any]]:
    """Parse SRT, WebVTT or timed JSON without making up timestamps.

    JSON may be a cue array or an object containing ``transcript``, ``segments``
    or ``cues``. Plain text is rejected because assigning times to it would make
    later cuts look precise when they are not.
    """

    if not isinstance(text, str) or not text.strip():
        raise SelectionError("Le transcript est vide.")
    stripped = text.lstrip("\ufeff \t\r\n")
    if stripped.startswith(("[", "{")):
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise SelectionError(f"JSON de transcript invalide : {exc.msg} (ligne {exc.lineno}).") from exc
        if isinstance(parsed, dict):
            for key in ("transcript", "segments", "cues"):
                if key in parsed:
                    parsed = parsed[key]
                    break
        if not isinstance(parsed, list):
            raise SelectionError(
                "JSON de transcript invalide : fournissez une liste de segments horodatés."
            )
        if not parsed:
            raise SelectionError("Le transcript JSON ne contient aucun segment.")
        return _validated_cues(parsed, preserve_ids=True)
    if "-->" in stripped or stripped.startswith("WEBVTT"):
        return _parse_subtitles(stripped)
    raise SelectionError(
        "Le texte fourni n'a pas d'horodatage. Importez un fichier SRT, VTT ou JSON "
        "avec start/end ; aucun timecode ne sera inventé."
    )


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()



def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _run_checked(
    args: Sequence[str],
    check: Check,
    *,
    timeout: float | None = None,
    input_text: str | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a process while still honoring cancellation during long Whisper calls."""

    try:
        process = subprocess.Popen(
            list(args),
            stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(cwd) if cwd is not None else None,
        )
    except OSError as exc:
        raise SelectionError(f"Impossible de lancer {args[0]} : {exc}") from exc
    started = time.monotonic()
    pending_input = input_text
    try:
        while True:
            check()
            if timeout is not None and time.monotonic() - started > timeout:
                raise SelectionError(f"{args[0]} a dépassé le délai de {timeout:g} s.")
            try:
                stdout, stderr = process.communicate(input=pending_input, timeout=0.25)
                break
            except subprocess.TimeoutExpired:
                # communicate drains both pipes while it waits, avoiding a
                # deadlock on verbose ffmpeg/Whisper processes.
                pending_input = None
    except BaseException:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        raise
    if process.returncode:
        detail = (stderr or stdout or "erreur inconnue").strip()[-1200:]
        raise SelectionError(f"{args[0]} a échoué ({process.returncode}) : {detail}")
    return subprocess.CompletedProcess(list(args), process.returncode, stdout, stderr)



def _tool(name: str, env_name: str) -> str:
    configured = os.environ.get(env_name)
    found = configured or shutil.which(name)
    if not found:
        raise SelectionError(f"Outil local requis introuvable : {name}")
    return found


def _whisper_model() -> Path:
    return Path(os.environ.get("WHISPER_MODEL", str(DEFAULT_WHISPER_MODEL))).expanduser().resolve()


def _require_whisper() -> tuple[str, Path]:
    executable = _tool("whisper-cli", "WHISPER_CLI")
    model = _whisper_model()
    if not model.is_file():
        raise SelectionError(
            f"Modèle Whisper local introuvable : {model}. Définissez WHISPER_MODEL."
        )
    return executable, model


def _extract_audio(
    source: Path,
    destination: Path,
    start: float,
    duration: float,
    check: Check,
) -> None:
    ffmpeg = _tool("ffmpeg", "FFMPEG")
    destination.unlink(missing_ok=True)
    _run_checked(
        [
            ffmpeg,
            "-y",
            "-v",
            "error",
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{duration:.3f}",
            "-i",
            str(source),
            "-vn",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(destination),
        ],
        check,
    )
    if not destination.is_file() or destination.stat().st_size <= 44:
        raise SelectionError("ffmpeg n'a pas produit l'audio demandé.")


def _whisper_srt(
    wav: Path,
    prefix: Path,
    max_len: int,
    check: Check,
    on_fraction: Callable[[float], None] | None = None,
    words: bool = False,
) -> list[dict[str, Any]]:
    whisper, model = _require_whisper()
    srt = Path(str(prefix) + ".srt")
    srt.unlink(missing_ok=True)
    args = [
        whisper, "-m", str(model), "-f", str(wav), "-l", os.environ.get("WHISPER_LANGUAGE", "fr"),
        "-osrt", "-ml", str(max_len), "-sow", "-np", "-of", str(prefix),
    ]
    if on_fraction is None:
        _run_checked(args, check)
    else:
        def on_line(line: str) -> None:
            fraction = proc.whisper_fraction(line)
            if fraction is not None:
                on_fraction(fraction)
        proc.stream(args + ["-pp"], check, on_line, error=SelectionError, label="Whisper")
    if not srt.is_file():
        raise SelectionError("Whisper a terminé sans produire de fichier SRT.")
    try:
        text = srt.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise SelectionError(f"Impossible de lire la sortie Whisper : {exc}") from exc
    return _parse_subtitles(text, words=True) if words else parse_transcript(text)


def _source_fingerprint(path: Path, source: dict[str, Any]) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "duration": source.get("duration"),
        "model": str(_whisper_model()),
        "language": os.environ.get("WHISPER_LANGUAGE", "fr"),
        "chunk_seconds": TRANSCRIBE_CHUNK_SECONDS,
        "overlap_seconds": TRANSCRIBE_OVERLAP_SECONDS,
    }


def _merge_chunk_cues(
    merged: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
    chunk_start: float,
    is_first: bool,
) -> list[dict[str, Any]]:
    absolute = [
        {"start": cue["start"] + chunk_start, "end": cue["end"] + chunk_start, "text": cue["text"]}
        for cue in incoming
    ]
    if is_first:
        return absolute
    # Split ownership halfway through the overlap. This prevents repeated cues
    # while retaining the untouched, Whisper-produced timestamps on either side.
    boundary = chunk_start + TRANSCRIBE_OVERLAP_SECONDS / 2
    kept = [cue for cue in merged if (cue["start"] + cue["end"]) / 2 < boundary]
    additions = [cue for cue in absolute if (cue["start"] + cue["end"]) / 2 >= boundary]
    return kept + additions


def _primary(project: dict[str, Any]) -> tuple[dict[str, Any], Path]:
    """The project's single file, already cut and framed upstream."""
    sources = project.get("sources") or []
    if not sources or not isinstance(sources[0], dict):
        raise SpeechError("Ajoutez d'abord la vidéo du reel.")
    source = sources[0]
    if source.get("has_audio") is not True:
        raise SpeechError("Cette vidéo ne contient pas de piste audio à transcrire.")
    raw_path = source.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        raise SpeechError("La vidéo du projet n'a pas de chemin local valide.")
    path = Path(raw_path).expanduser().resolve()
    if not path.is_file():
        raise SpeechError(f"Vidéo introuvable : {path}")
    duration = source.get("duration")
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(float(duration)) or duration <= 0:
        raise SpeechError("Durée de la vidéo invalide.")
    return source, path


def transcribe(
    project: dict[str, Any],
    out_dir: Path,
    progress: Progress = _noop_progress,
    check: Check = _noop_check,
) -> list[dict[str, Any]]:
    """Transcribe the project's video into sentence cues, in resumable chunks."""
    source, path = _primary(project)
    return transcribe_media(path, float(source["duration"]), out_dir, progress, check)


def transcribe_media(
    path: Path,
    duration: float,
    out_dir: Path,
    progress: Progress = _noop_progress,
    check: Check = _noop_check,
    words: bool = False,
) -> list[dict[str, Any]]:
    """Cues for one local file. ``words=True`` returns one cue per spoken word."""
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise SpeechError(f"Fichier introuvable : {path}")
    _require_whisper()
    _tool("ffmpeg", "FFMPEG")
    output = Path(out_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    fingerprint = _source_fingerprint(path, {"duration": duration})
    fingerprint["words"] = words
    cache_dir = output / ("transcription-" + _digest(fingerprint)[:16])
    cache_dir.mkdir(parents=True, exist_ok=True)
    step = TRANSCRIBE_CHUNK_SECONDS - TRANSCRIBE_OVERLAP_SECONDS
    starts: list[float] = []
    cursor = 0.0
    while cursor < duration:
        starts.append(cursor)
        cursor += step

    merged: list[dict[str, Any]] = []
    for index, start in enumerate(starts):
        check()
        chunk_duration = min(TRANSCRIBE_CHUNK_SECONDS, duration - start)
        checkpoint = cache_dir / f"chunk-{index:04d}.json"
        cues: list[dict[str, Any]] | None = None
        if checkpoint.is_file():
            try:
                saved = json.loads(checkpoint.read_text(encoding="utf-8"))
                if (saved.get("fingerprint") == fingerprint
                        and abs(float(saved.get("start")) - start) < 0.001
                        and abs(float(saved.get("duration")) - chunk_duration) < 0.001):
                    cues = list(saved.get("cues") or [])
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                cues = None
        if cues is None:
            share = 100 / max(1, len(starts))
            label = "Transcription" if len(starts) == 1 else f"Transcription du bloc {index + 1}/{len(starts)}"
            progress(index * share, f"Extraction de l’audio · {label.lower()}")
            wav = cache_dir / f"chunk-{index:04d}.wav"
            prefix = cache_dir / f"whisper-{index:04d}"

            def on_fraction(fraction: float, base: float = index * share) -> None:
                progress(base + share * (0.06 + 0.94 * fraction), f"{label} en cours")

            try:
                _extract_audio(path, wav, start, chunk_duration, check)
                progress(index * share + share * 0.06, f"{label} · chargement du modèle")
                cues = _whisper_srt(wav, prefix, 1 if words else 80, check, on_fraction, words=words)
            finally:
                wav.unlink(missing_ok=True)
                Path(str(prefix) + ".srt").unlink(missing_ok=True)
            _atomic_json(checkpoint, {"fingerprint": fingerprint, "start": start, "duration": chunk_duration, "cues": cues})
        else:
            progress(index * 100 / max(1, len(starts)), f"Reprise du bloc {index + 1}/{len(starts)}")
        merged = _merge_chunk_cues(merged, cues, start, index == 0)

    progress(100, "Transcription terminée")
    if words:
        kept = [cue for cue in _drop_credit_hallucinations(merged) if cue["text"].strip()]
        if not kept:
            raise SpeechError("Whisper n'a détecté aucune parole dans cette vidéo.")
        return [{"start": round(c["start"], 3), "end": round(max(c["start"], c["end"]), 3), "text": c["text"].strip()}
                for c in sorted(kept, key=lambda c: (c["start"], c["end"]))]
    final = _validated_cues(_drop_credit_hallucinations(merged), preserve_ids=False)
    if not final:
        raise SpeechError("Whisper n'a détecté aucune parole dans cette vidéo.")
    return final


# Whisper fills silences with TV subtitle credits it learned in training. They were
# never spoken, so a cue made only of them is removed outright.
_CREDIT_HALLUCINATIONS = (
    "sous-titrage societe radio-canada", "sous titrage societe radio canada", "sous-titrage st' 501",
    "sous-titres realises par la communaute d'amara.org", "sous-titres realises par l'amara.org",
    "merci d'avoir regarde", "merci d'avoir regarde cette video", "abonnez-vous", "sous-titrage",
)


def _drop_credit_hallucinations(cues: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    def normal(text: str) -> str:
        plain = "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")
        return " ".join(plain.strip(" .!?…").split())
    return [cue for cue in cues if normal(cue["text"]) not in _CREDIT_HALLUCINATIONS]


def status() -> dict[str, Any]:
    """What the machine can do locally, for the diagnostics panel."""
    model = _whisper_model()
    return {
        "whisper_cli": os.environ.get("WHISPER_CLI") or shutil.which("whisper-cli"),
        "model": str(model),
        "model_ready": model.is_file(),
        "language": os.environ.get("WHISPER_LANGUAGE", "fr"),
    }
