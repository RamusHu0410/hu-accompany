"""Reading MusicXML out of PDMX's .mxl files and sanity-checking it.

Framework-free so the import command and the tests share one code path.
"""

import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


class InvalidMusicXML(ValueError):
    """The file is not a score we can render and practise against."""


@dataclass(frozen=True)
class ScoreFacts:
    part_count: int
    measure_count: int
    time_signature: str
    tempo_bpm: float | None


def read_musicxml(path: Path) -> bytes:
    """The uncompressed MusicXML inside `path`, which may be a compressed
    .mxl container or already-plain .xml / .musicxml."""
    if not zipfile.is_zipfile(path):
        return path.read_bytes()

    try:
        with zipfile.ZipFile(path) as z:
            return z.read(_rootfile(z))
    except (zipfile.BadZipFile, KeyError) as e:
        raise InvalidMusicXML(f"unreadable .mxl container: {e}") from e


def _rootfile(z: zipfile.ZipFile) -> str:
    # META-INF/container.xml names the score; fall back to the first XML
    # file for containers that omit it.
    try:
        container = ET.fromstring(z.read("META-INF/container.xml"))
        elem = container.find(".//{*}rootfile")
        if elem is not None and elem.attrib.get("full-path"):
            return elem.attrib["full-path"]
    except (KeyError, ET.ParseError):
        pass

    for name in z.namelist():
        if name.lower().endswith((".xml", ".musicxml")) and not name.startswith("META-INF/"):
            return name
    raise InvalidMusicXML("no MusicXML file inside the .mxl container")


def inspect(xml: bytes) -> ScoreFacts:
    """Checks the score has parts, measures and notes, and reads the facts
    the app needs up front. Raises InvalidMusicXML otherwise."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as e:
        raise InvalidMusicXML(f"not well-formed XML: {e}") from e

    # OSMD renders partwise scores; timewise ones are rare enough in PDMX
    # to skip rather than convert.
    if root.tag != "score-partwise":
        raise InvalidMusicXML(f"unsupported root element <{root.tag}>")

    parts = root.findall("part")
    if not parts:
        raise InvalidMusicXML("score has no parts")

    measure_count = max(len(part.findall("measure")) for part in parts)
    if measure_count == 0:
        raise InvalidMusicXML("score has no measures")
    if root.find(".//note/pitch") is None:
        raise InvalidMusicXML("score has no pitched notes")

    return ScoreFacts(
        part_count=len(parts),
        measure_count=measure_count,
        time_signature=_first_time_signature(root),
        tempo_bpm=_first_tempo(root),
    )


def _first_time_signature(root: ET.Element) -> str:
    time = root.find(".//attributes/time")
    if time is None:
        return ""
    beats = time.findtext("beats", "").strip()
    beat_type = time.findtext("beat-type", "").strip()
    return f"{beats}/{beat_type}" if beats and beat_type else ""


def _first_tempo(root: ET.Element) -> float | None:
    # <sound tempo> is the playback value; <metronome> is only the printed
    # marking, so it is the fallback.
    sound = root.find(".//sound[@tempo]")
    candidates = [
        sound.attrib["tempo"] if sound is not None else None,
        root.findtext(".//metronome/per-minute"),
    ]
    for value in candidates:
        try:
            bpm = float(value)
        except (TypeError, ValueError):
            continue
        if bpm > 0:
            return bpm
    return None
