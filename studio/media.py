"""Local, deterministic media operations for the studio.

Every public operation either returns a verified artifact or raises.  Commands
are always argument vectors, temporary files live below the caller's output
directory, and final names only become visible after validation.
"""

from __future__ import annotations

from . import proc
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterable


Progress = Callable[[int, str], None]
Check = Callable[[], None]

PIPELINE_VERSION = 3
PROXY_FORMAT = "h264-720p-natif-gop10"
# Le reel arrive déjà cadré : le proxy garde son format, il ne fait que réduire la définition.
PROXY_LONG_EDGE = 1280
PROXY_SHORT_EDGE = 720


class MediaError(RuntimeError):
    """An external media operation failed or produced an invalid artifact."""


def _noop() -> None:
    return None


def _run(
    args: Iterable[object],
    *,
    check: Check = _noop,
    label: str = "commande media",
    ok_codes: tuple[int, ...] = (0,),
) -> subprocess.CompletedProcess[str]:
    """Run a cancellable process without invoking a shell."""
    command = [str(value) for value in args]
    check()
    try:
        proc = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as exc:
        raise MediaError(f"Impossible de lancer {command[0]}: {exc}") from exc
    try:
        while True:
            try:
                stdout, stderr = proc.communicate(timeout=0.20)
                break
            except subprocess.TimeoutExpired:
                check()
    except BaseException:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        raise
    if proc.returncode not in ok_codes:
        detail = (stderr or stdout or "aucun diagnostic").strip()[-2400:]
        raise MediaError(f"{label} a echoue (code {proc.returncode}): {detail}")
    return subprocess.CompletedProcess(command, proc.returncode, stdout, stderr)


def _tool(name: str, env_name: str | None = None) -> str | None:
    if env_name and os.environ.get(env_name):
        candidate = Path(os.environ[env_name]).expanduser()
        return str(candidate.resolve()) if candidate.is_file() else None
    found = shutil.which(name)
    if found:
        return str(Path(found).resolve())
    return None


def _required_tool(name: str, env_name: str | None = None) -> str:
    path = _tool(name, env_name)
    if not path:
        raise MediaError(f"Outil requis introuvable: {name}")
    return path


def _json_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]



def _source_fingerprint(source: dict[str, Any]) -> dict[str, Any]:
    path = Path(source["path"]).expanduser().resolve()
    stat = path.stat()
    return {
        "path": str(path),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "offset": float(source.get("offset", 0) or 0),
    }


def _parse_rate(value: str | None) -> float:
    if not value or value == "0/0":
        return 0.0
    if "/" in value:
        num, den = value.split("/", 1)
        return float(num) / float(den) if float(den) else 0.0
    return float(value)


def _probe_raw(path: Path, check: Check = _noop) -> dict[str, Any]:
    ffprobe = _required_tool("ffprobe")
    result = _run(
        [
            ffprobe,
            "-v", "error",
            "-show_streams",
            "-show_format",
            "-of", "json",
            str(path),
        ],
        check=check,
        label=f"ffprobe de {path.name}",
    )
    try:
        return json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError) as exc:
        raise MediaError(f"ffprobe a renvoye un JSON invalide pour {path}") from exc


def probe(path: str | os.PathLike[str]) -> dict[str, Any]:
    """Return normalized source metadata and reject undecodable media."""
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise MediaError(f"Media introuvable: {resolved}")
    data = _probe_raw(resolved)
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if not video:
        raise MediaError(f"Aucune piste video dans {resolved.name}")
    try:
        duration = float(data.get("format", {}).get("duration") or video.get("duration"))
        width, height = int(video["width"]), int(video["height"])
    except (TypeError, ValueError, KeyError) as exc:
        raise MediaError(f"Metadonnees video incompletes: {resolved.name}") from exc
    if not math.isfinite(duration) or duration <= 0 or width <= 0 or height <= 0:
        raise MediaError(f"Metadonnees video invalides: {resolved.name}")
    fps = _parse_rate(video.get("avg_frame_rate") or video.get("r_frame_rate"))
    # Cadence nominale : une source à images manquantes a une moyenne fausse (29,977 pour du 30).
    rate = _parse_rate(video.get("r_frame_rate")) or fps
    return {
        "path": str(resolved),
        "name": resolved.name,
        "width": width,
        "height": height,
        "duration": duration,
        "fps": fps,
        "rate": rate,
        "has_audio": any(s.get("codec_type") == "audio" for s in data.get("streams", [])),
    }


def _font_dirs() -> list[Path]:
    configured = [Path(p).expanduser() for p in os.environ.get("STUDIO_FONT_DIRS", "").split(os.pathsep) if p]
    return configured + [
        Path.home() / "Library" / "Fonts",
        Path("/Library/Fonts"),
        Path("/System/Library/Fonts"),
        Path.home() / ".local" / "share" / "fonts",
        Path("/usr/local/share/fonts"),
        Path("/usr/share/fonts"),
    ]


def _installed_fonts() -> list[str]:
    result: list[str] = []
    for directory in _font_dirs():
        if not directory.is_dir():
            continue
        try:
            for path in directory.rglob("*"):
                if path.is_file() and path.suffix.lower() in {".otf", ".ttf", ".ttc"}:
                    result.append(str(path.resolve()))
        except OSError:
            continue
    return sorted(set(result), key=lambda p: p.casefold())




def diagnostics() -> dict[str, Any]:
    """Report local dependencies without claiming that optional tools exist."""
    tools: list[dict[str, Any]] = []
    for name, env_name in (("ffmpeg", None), ("ffprobe", None)):
        path = _tool(name, env_name)
        detail = ""
        if path:
            try:
                result = _run([path, "-version"], label=f"diagnostic {name}")
                detail = ((result.stdout or result.stderr).splitlines() or [""])[0]
            except MediaError:
                detail = "installe, version non disponible"
        tools.append({"name": name, "available": bool(path), "path": path, "detail": detail})
    # whisper-cli prints backend logs instead of a version line, so only presence is reported.
    whisper = _tool("whisper-cli", "WHISPER_CLI")
    tools.append({"name": "whisper-cli", "available": bool(whisper), "path": whisper, "detail": ""})
    model = Path(
        os.environ.get("WHISPER_MODEL", str(Path.home() / ".cache/whisper-cpp/ggml-large-v3-turbo.bin"))
    ).expanduser()
    tools.append({
        "name": "modèle Whisper",
        "available": model.is_file(),
        "path": str(model) if model.is_file() else None,
        "detail": model.name,
    })
    return {"tools": tools, "fonts": _installed_fonts()}


def _verify_video(
    path: Path,
    *,
    expected_duration: float | None = None,
    dimensions: tuple[int, int] | None = None,
    require_audio: bool = True,
    check: Check = _noop,
    full_decode: bool = True,
) -> dict[str, Any]:
    info = probe(path)
    if dimensions and (info["width"], info["height"]) != dimensions:
        raise MediaError(
            f"Dimensions produites invalides: {info['width']}x{info['height']} au lieu de {dimensions[0]}x{dimensions[1]}"
        )
    if require_audio and not info["has_audio"]:
        raise MediaError("Le fichier produit ne contient pas de piste audio")
    if expected_duration is not None:
        tolerance = max(0.16, 2.5 / max(info["fps"], 24.0))
        if abs(info["duration"] - expected_duration) > tolerance:
            raise MediaError(
                f"Duree produite invalide: {info['duration']:.3f}s au lieu de {expected_duration:.3f}s"
            )
    ffmpeg = _required_tool("ffmpeg")
    decode_args = [ffmpeg, "-v", "error", "-i", str(path)]
    if not full_decode:
        decode_args += ["-frames:v", "1"]
    decode_args += ["-map", "0:v:0", "-map", "0:a:0?", "-f", "null", "-"]
    _run(decode_args, check=check, label=f"decodage de controle de {path.name}")
    return info




def _proxy_size(info: dict[str, Any]) -> tuple[int, int]:
    """La définition du proxy, au format d'origine : le grand côté à 1280, le petit à 720 au plus."""
    width, height = max(1, int(info["width"])), max(1, int(info["height"]))
    long_edge, short_edge = max(width, height), min(width, height)
    ratio = min(PROXY_LONG_EDGE / long_edge, PROXY_SHORT_EDGE / short_edge, 1.0)
    return max(2, int(width * ratio) // 2 * 2), max(2, int(height * ratio) // 2 * 2)


def make_proxy(
    source: dict[str, Any],
    out_dir: Path,
    progress: Progress,
    check: Check,
) -> dict[str, Any]:
    """Un proxy 720p au format d'origine, avec une image-clé toutes les dix images pour une timeline fluide."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    check()
    info = probe(source["path"])
    duration = float(info["duration"])
    if duration <= 0:
        raise MediaError("La source ne dure rien : proxy impossible")
    width, height = _proxy_size(info)
    manifest = {
        "version": PIPELINE_VERSION,
        "operation": "proxy",
        "source": _source_fingerprint(source),
        "duration": round(duration, 6),
        "size": [width, height],
        # Les anciens proxys letterboxés ont le même manifeste : sans cette clé, ils seraient repris puis refusés.
        "proxy_format": PROXY_FORMAT,
    }
    digest = _json_hash(manifest)
    final = out_dir / f"proxy-{digest}.mp4"
    if final.exists():
        info = _verify_video(final, expected_duration=duration, dimensions=(width, height),
                             require_audio=info["has_audio"], check=check, full_decode=False)
        return {"path": str(final), **info}

    ffmpeg = _required_tool("ffmpeg")
    progress(5, "Préparation du proxy")
    with tempfile.TemporaryDirectory(prefix=".proxy-", dir=out_dir) as temp_name:
        staged = Path(temp_name) / "proxy.mp4"
        fps = info["fps"] or 25.0
        args = [ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-y",
                "-i", str(Path(source["path"]).expanduser().resolve()),
                "-vf", f"scale={width}:{height}:flags=lanczos,setsar=1,format=yuv420p",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-g", "10", "-keyint_min", "10", "-sc_threshold", "0"]
        if info["has_audio"]:
            args += ["-c:a", "aac", "-b:a", "128k", "-ar", "48000"]
        else:
            args += ["-an"]
        args += ["-movflags", "+faststart", "-progress", "pipe:1", "-nostats", str(staged)]
        seen = [0.0]

        def on_line(line: str) -> None:
            fraction = proc.ffmpeg_fraction(line, duration)
            if fraction is not None and fraction - seen[0] >= 0.02:
                seen[0] = fraction
                progress(5 + fraction * 80, "Encodage du proxy")
        proc.stream(args, check, on_line, error=MediaError, label="L’encodage du proxy")
        progress(88, "Vérification du proxy")
        _verify_proxy_gop(staged, fps, check)
        info = _verify_video(staged, expected_duration=duration, dimensions=(width, height),
                             require_audio=info["has_audio"], check=check, full_decode=False)
        check()
        os.replace(staged, final)
        info.update(path=str(final.resolve()), name=final.name)
    progress(100, "Proxy terminé")
    return {"path": str(final), **info}


def export_name(name: str) -> str:
    """Un nom de fichier lisible, tiré du nom du short."""
    cleaned = re.sub(r"[^\w .,'()\u00c0-\u017f-]+", " ", str(name or "Montage")).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)[:120].strip(" .") or "Montage"
    return cleaned


def free_path(directory: Path, stem: str, suffix: str = ".mp4") -> Path:
    """Le premier nom libre : on n'écrase jamais un montage déjà exporté."""
    directory = Path(directory)
    target, n = directory / f"{stem}{suffix}", 2
    while target.exists():
        target = directory / f"{stem} ({n}){suffix}"
        n += 1
    return target


def export_montage(
    source_path: str | os.PathLike[str],
    segments: list[dict[str, float]],
    target: Path,
    progress: Progress,
    check: Check,
    overlay: dict[str, Any] | None = None,
    encoder: list[str] | None = None,
) -> dict[str, Any]:
    """Le montage validé : les morceaux gardés bout à bout, dans un MP4 à côté du rush.

    Rien à couper : on remuxe, les images d'origine passent telles quelles. Sinon il faut
    réencoder une fois — couper à l'image près au milieu d'un GOP est impossible en copie
    de flux, et un montage calé sur les keyframes se décalerait de plusieurs secondes.

    ``overlay`` pose une image par-dessus le montage — l'encadré d'accroche — dans la même
    passe que les coupes : une seule réécriture des images, jamais deux. Elle interdit le
    remux, forcément : les images changent.
    """
    source = Path(source_path).expanduser().resolve()
    if not source.is_file():
        raise MediaError("Le rush est introuvable à son emplacement d’origine")
    pieces = [(max(0.0, float(s["start"])), float(s["end"])) for s in segments if float(s["end"]) > float(s["start"])]
    if not pieces:
        raise MediaError("Le montage ne garde aucun morceau : rien à exporter")
    check()
    info = probe(source)
    # fps = cadence nominale (r_frame_rate), pas la moyenne : sur une source à images manquantes
    # la moyenne (29,977 pour du 30) décale la grille et l'encodage de sortie.
    duration, fps = float(info["duration"]), info.get("rate") or info["fps"] or 25.0
    # Bornes calées sur la grille des images : trim coupe la vidéo à l'image près mais atrim coupe
    # le son au centième. Sans ce calage, chaque morceau ajoute jusqu'à une image de vidéo en trop :
    # 51 morceaux à 25 i/s donnaient 0,18 s d'écart (export refusé) et le son dérivait sous l'image.
    pieces = [(round(a * fps) / fps, round(b * fps) / fps) for a, b in pieces]
    pieces = [(a, b) for a, b in pieces if b > a]
    if not pieces:
        raise MediaError("Le montage ne garde aucun morceau : rien à exporter")
    expected = round(sum(b - a for a, b in pieces), 3)
    whole = len(pieces) == 1 and pieces[0][0] <= 0.05 and pieces[0][1] >= duration - 0.05 and not overlay
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = _required_tool("ffmpeg")
    progress(5, "Préparation de l’export")
    with tempfile.TemporaryDirectory(prefix=".export-", dir=target.parent) as temp_name:
        staged = Path(temp_name) / "montage.mp4"
        # -reinit_filter 0 : une source dont les images changent de format en cours de route (plage
        # pleine puis plage vidéo, comme une caméra DJI montée avec un enregistrement d'écran) faisait
        # réinitialiser tout le graphe de filtres au changement. Trim et concat repartaient de zéro et
        # l'export perdait des minutes (Masterclass LinkedIn, 06/11 : 1138 s au lieu de 1237 s).
        # Le graphe reste en place, et la première étape ramène chaque image à la même plage.
        args = [ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-y"]
        if not whole:
            args += ["-reinit_filter", "0"]
        args += ["-i", str(source)]
        if overlay:
            args += ["-loop", "1", "-t", f"{float(overlay['seconds']):.3f}", "-i", str(overlay["path"])]
        if whole:
            args += ["-map", "0:v:0", "-c", "copy"]
            if info["has_audio"]:
                args += ["-map", "0:a:0"]
        else:
            graph, outs = [], []
            # Vidéo : bornes reculées d'une demi-image, pour que trim prenne exactement les images
            # de [a, b[ malgré l'arrondi (à 30 i/s, 14,9667 s écrit 14,967 tombait entre deux images
            # et le morceau perdait une image que le son gardait). Son : bornes au micro-seconde.
            # Puis chaque morceau vidéo est remis à cadence fixe et forcé à la durée exacte de son
            # son (dernière image prolongée si la source a sauté une image) : les écarts ne peuvent
            # plus s'additionner, même sur 65 morceaux après « Supprimer les blancs ».
            half = 0.5 / fps
            # Matrice imposée en HD : la DJI ne l'écrit pas dans ses images, et sans elle la conversion
            # de plage changeait aussi la matrice (bt601 -> bt709) et assombrissait l'ouverture (06/11).
            matrice = "in_color_matrix=bt709:out_color_matrix=bt709:" if min(info["width"], info["height"]) >= 720 else ""
            graph.append(f"[0:v]scale={matrice}out_range=tv,format=yuv420p,split={len(pieces)}"
                         + "".join(f"[src{i}]" for i in range(len(pieces))))
            for index, (a, b) in enumerate(pieces):
                graph.append(f"[src{index}]trim=start={max(0.0, a - half):.6f}:end={b - half:.6f},setpts=PTS-STARTPTS,"
                             f"fps={fps:.6f},tpad=stop_mode=clone:stop_duration=1,"
                             f"trim=duration={b - a - half:.6f}[v{index}]")
                outs.append(f"[v{index}]")
                if info["has_audio"]:
                    graph.append(f"[0:a]atrim=start={a:.6f}:end={b:.6f},asetpts=PTS-STARTPTS[a{index}]")
                    outs.append(f"[a{index}]")
            graph.append("".join(outs) + f"concat=n={len(pieces)}:v=1:a={1 if info['has_audio'] else 0}[v]"
                         + ("[a]" if info["has_audio"] else ""))
            video = "[v]"
            if overlay:
                # L'encadré est posé dès la première image et s'efface tout seul ; passé sa durée,
                # eof_action=pass laisse couler le montage.
                graph.append(f"[1:v]format=rgba,scale={info['width']}:{info['height']},"
                             f"fade=t=out:st={float(overlay['fade_start']):.3f}:"
                             f"d={float(overlay['fade_seconds']):.3f}:alpha=1[carte]")
                graph.append("[v][carte]overlay=eof_action=pass,format=yuv420p[vo]")
                video = "[vo]"
            args += ["-filter_complex", ";".join(graph), "-map", video]
            if info["has_audio"]:
                args += ["-map", "[a]", "-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
            else:
                args += ["-an"]
            args += list(encoder or ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                                     "-pix_fmt", "yuv420p", "-r", f"{fps:.6f}"])
            args += ["-color_range", "tv"]
            if min(info["width"], info["height"]) >= 720:
                args += ["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709"]
        args += ["-movflags", "+faststart", "-progress", "pipe:1", "-nostats", str(staged)]
        seen = [0.0]

        def on_line(line: str) -> None:
            fraction = proc.ffmpeg_fraction(line, expected)
            if fraction is not None and fraction - seen[0] >= 0.02:
                seen[0] = fraction
                progress(5 + fraction * 85, "Remux du montage" if whole else "Encodage du montage")
        proc.stream(args, check, on_line, error=MediaError, label="L’export du montage")
        progress(92, "Vérification de l’export")
        made = _verify_video(staged, expected_duration=expected, require_audio=info["has_audio"],
                             check=check, full_decode=False)
        check()
        final = free_path(target.parent, target.stem, target.suffix)
        os.replace(staged, final)
    progress(100, "Export terminé")
    return {"path": str(final), "duration": made["duration"], "expected": expected,
            "pieces": len(pieces), "remux": whole, "encadre": bool(overlay),
            "bytes": Path(final).stat().st_size}


def _verify_proxy_gop(path: Path, fps: float, check: Check) -> None:
    """Une image-clé toutes les dix images est le contrat de fluidité de la timeline."""
    probe_tool = _required_tool("ffprobe")
    # Lire toutes les images d'un rush de 24 min annulerait le gain du proxy.
    # La contrainte d'encodage impose le GOP ; on contrôle la première fenêtre de 12 s.
    result = _run([probe_tool, "-v", "error", "-read_intervals", "0%+12", "-select_streams", "v:0", "-show_entries", "frame=key_frame,best_effort_timestamp_time", "-of", "csv=p=0", str(path)], check=check, label="contrôle des images-clés du proxy")
    times = []
    for line in result.stdout.splitlines():
        fields = line.split(",")
        if fields and fields[0] == "1":
            for field in reversed(fields[1:]):
                try:
                    times.append(float(field)); break
                except ValueError:
                    continue
    if len(times) < 2 or max(b-a for a, b in zip(times, times[1:])) > 10 / max(fps, 1) * 1.35:
        raise MediaError("Proxy refusé : intervalle d’images-clés supérieur à dix images")


