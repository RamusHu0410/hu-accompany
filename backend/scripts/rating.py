# Judging file


# Right here I want you to compare the the 2 files test_notes.json and user_test.json and tell me if they are the same or different. If they are different,
# Identify the differences in notes (pitch accuracy)

# And output the differences in a json format like this:
# [
# {"start": 0.0, "duration": 1.0, "user_hz": 137.813, "test_hz": 130.813, "advise": "The pitch is higher than expected. Try to lower the pitch to match the test note.", "details": "The user played a note at 137.813 Hz, while the test note was at 130.813 Hz. This indicates that the user's pitch is higher than the expected pitch."}
#   ]
#
# Something like that

import json
import math
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
TEST_NOTES_PATH = BASE_DIR / "test_notes.json"
USER_NOTES_PATH = BASE_DIR / "user_test.json"

# Anything within this many cents (1/100th of a semitone) is considered in tune.
CENTS_TOLERANCE = 10.0


def load_notes(path):
    with open(path, "r") as f:
        data = json.load(f)
    return data.get("notes", [])


def hz_to_cents(user_hz, test_hz):
    return 1200 * math.log2(user_hz / test_hz)


def group_by_time(notes):
    groups = {}
    for note in notes:
        key = (round(note["start"], 3), round(note["duration"], 3))
        groups.setdefault(key, []).append(note)
    return groups


def build_pitch_diff(start, duration, user_hz, test_hz, cents):
    direction = "higher" if cents > 0 else "lower"
    opposite = "lower" if cents > 0 else "higher"
    return {
        "start": start,
        "duration": duration,
        "user_hz": user_hz,
        "test_hz": test_hz,
        "advise": f"The pitch is {direction} than expected. Try to {opposite} the pitch to match the test note.",
        "details": (
            f"The user played a note at {user_hz} Hz, while the test note was at {test_hz} Hz. "
            f"This indicates that the user's pitch is {direction} than the expected pitch."
        ),
    }


def build_missing_diff(start, duration, test_hz):
    return {
        "start": start,
        "duration": duration,
        "user_hz": None,
        "test_hz": test_hz,
        "advise": "This note is missing. Try to play the note.",
        "details": f"The test expected a note at {test_hz} Hz, but the user did not play it.",
    }


def build_extra_diff(start, duration, user_hz):
    return {
        "start": start,
        "duration": duration,
        "user_hz": user_hz,
        "test_hz": None,
        "advise": "An extra note was played. Try not to play a note here.",
        "details": f"The user played a note at {user_hz} Hz that was not expected at this point.",
    }


def compare_notes(test_notes, user_notes):
    differences = []
    test_groups = group_by_time(test_notes)
    user_groups = group_by_time(user_notes)

    for start, duration in sorted(set(test_groups) | set(user_groups)):
        test_chord = sorted(test_groups.get((start, duration), []), key=lambda n: n["hz"])
        user_chord = sorted(user_groups.get((start, duration), []), key=lambda n: n["hz"])

        for test_note, user_note in zip(test_chord, user_chord):
            cents = hz_to_cents(user_note["hz"], test_note["hz"])
            if abs(cents) > CENTS_TOLERANCE:
                differences.append(
                    build_pitch_diff(start, duration, user_note["hz"], test_note["hz"], cents)
                )

        if len(test_chord) > len(user_chord):
            differences.extend(
                build_missing_diff(start, duration, note["hz"])
                for note in test_chord[len(user_chord):]
            )
        elif len(user_chord) > len(test_chord):
            differences.extend(
                build_extra_diff(start, duration, note["hz"])
                for note in user_chord[len(test_chord):]
            )

    return differences


def rate_performance(test_path=TEST_NOTES_PATH, user_path=USER_NOTES_PATH):
    test_notes = load_notes(test_path)
    user_notes = load_notes(user_path)
    differences = compare_notes(test_notes, user_notes)
    return {"same": len(differences) == 0, "differences": differences}


if __name__ == "__main__":
    result = rate_performance()
    if result["same"]:
        print("The files are the same.")
    else:
        print("The files are different.")
    print(json.dumps(result["differences"], indent=2))
