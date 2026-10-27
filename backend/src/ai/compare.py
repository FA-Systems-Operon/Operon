"""US 2.2 comparison: baseline vs. Brain-assisted prompt on the same transcripts.

Runs both prompts on every transcript with the same provider and settings, saves
the paired raw replies, copies them to a blinded A/B folder for scoring, and
fills in the automated rubric checks (docs/evaluation/us-2.2-rubric.md).

Run it in the api container from the repo root (Ollama must be running on the host):

    docker compose run --rm -v ./tests/fixtures:/code/tests/fixtures api \
        python -m src.ai.compare \
        tests/fixtures/baseline/transcript_*.txt \
        tests/fixtures/comparison/transcript_*.txt \
        --brain-context tests/fixtures/brain/fa_systems_context.json \
        --expected-dir tests/fixtures/comparison/expected \
        --out-dir tests/fixtures/comparison/run
"""

import argparse
import csv
import hashlib
import json
import random
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

from src.ai.baseline import (
    BaselineOutputError,
    duplicate_stems,
    parse_client_profile,
    resolve_inside,
    run_baseline,
)
from src.ai.baseline_prompt import build_baseline_client_profile_prompt
from src.ai.brain_prompt import (
    build_brain_assisted_client_profile_prompt,
    load_brain_context,
)
from src.ai.provider import ModelProvider, ProviderError, get_provider

VERSIONS = ("baseline", "brain_assisted")
PROFILE_KEYS = {"name", "needs", "goals"}


def format_passes(text: str) -> bool:
    """Rubric format check: a valid profile with exactly name, needs and goals."""
    try:
        profile = parse_client_profile(text)
    except BaselineOutputError:
        return False
    return set(profile) == PROFILE_KEYS


def name_correct(text: str, expected_name: str | None) -> bool:
    """Rubric name check: matches the reference name, or is JSON null when it is."""
    try:
        profile = json.loads(text)
    except json.JSONDecodeError:
        return False
    if not isinstance(profile, dict) or "name" not in profile:
        return False
    name = profile["name"]
    if expected_name is None:
        return name is None
    return isinstance(name, str) and name.strip() == expected_name


def run_version(transcript, out_dir, provider, build_prompt, retries) -> Path:
    """Run one prompt on one transcript, retrying provider errors only.

    A malformed reply is not retried: it is a result to score, and with a fixed
    seed a retry would give the same answer anyway.
    """
    for attempt in range(retries + 1):
        try:
            return run_baseline(transcript, out_dir, provider, build_prompt).raw_path
        except BaselineOutputError:
            return out_dir / f"{Path(transcript).stem}.raw.json"
        except ProviderError:
            if attempt == retries:
                raise
    raise AssertionError("unreachable")  # pragma: no cover


def run_comparison(
    transcripts: list[Path],
    out_dir: Path,
    provider: ModelProvider,
    brain_context: str,
    rng: random.Random,
    retries: int = 2,
) -> dict[str, dict[str, str]]:
    """Run both prompts on each transcript and blind the pairs.

    Returns the blinding key: {transcript stem: {"A": version, "B": version}}.
    A transcript whose provider call keeps failing raises ProviderError, so a
    pair is never left half-saved without the caller knowing.
    """
    builders = {
        "baseline": build_baseline_client_profile_prompt,
        "brain_assisted": partial(
            build_brain_assisted_client_profile_prompt, brain_context=brain_context
        ),
    }
    blinded_dir = out_dir / "blinded"
    blinded_dir.mkdir(parents=True, exist_ok=True)

    key = {}
    for transcript in transcripts:
        raw_paths = {
            version: run_version(
                transcript, out_dir / version, provider, builders[version], retries
            )
            for version in VERSIONS
        }
        order = list(VERSIONS)
        rng.shuffle(order)
        stem = Path(transcript).stem
        key[stem] = dict(zip(("A", "B"), order, strict=True))
        for label, version in key[stem].items():
            text = raw_paths[version].read_text(encoding="utf-8")
            (blinded_dir / f"{stem}.{label}.json").write_text(text, encoding="utf-8")
    return key


def write_auto_scores(out_dir: Path, key: dict, expected_dir: Path) -> Path:
    """Fill in the rubric's automated columns for each blinded output."""
    path = out_dir / "auto_scores.csv"
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["transcript", "output", "format_pass", "name_correct"])
        for stem, labels in key.items():
            expected = json.loads(
                (expected_dir / f"{stem}.expected.json").read_text(encoding="utf-8")
            )
            for label in labels:
                text = (out_dir / "blinded" / f"{stem}.{label}.json").read_text(
                    encoding="utf-8"
                )
                writer.writerow(
                    [
                        stem,
                        label,
                        format_passes(text),
                        name_correct(text, expected["name"]),
                    ]
                )
    return path


def write_run_metadata(out_dir, root, transcripts, brain_path, provider) -> Path:
    """Record what was run, so the pairs can be traced and repeated."""
    metas = sorted((out_dir / "baseline").glob("*.meta.json"))
    model = json.loads(metas[0].read_text())["model"] if metas else None
    metadata = {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "provider": getattr(provider, "name", None),
        "model": model,
        "settings": "temperature 0, seed 42 (fixed in src/ai/ollama.py)",
        "transcripts": [str(path.relative_to(root)) for path in transcripts],
        "prompts": {
            "baseline": "build_baseline_client_profile_prompt",
            "brain_assisted": "build_brain_assisted_client_profile_prompt",
        },
        "brain_context": {
            "file": str(brain_path.relative_to(root)),
            "sha256": hashlib.sha256(brain_path.read_bytes()).hexdigest(),
        },
    }
    path = out_dir / "run_metadata.json"
    path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("transcripts", nargs="+", type=Path)
    parser.add_argument("--brain-context", type=Path, required=True)
    parser.add_argument("--expected-dir", type=Path)
    parser.add_argument("--out-dir", type=Path, default=Path("comparison_output"))
    args = parser.parse_args(argv)

    # Same rule as the baseline script: only read and write under the run directory.
    root = Path.cwd().resolve()
    try:
        transcripts = [resolve_inside(path, root) for path in args.transcripts]
        brain_path = resolve_inside(args.brain_context, root)
        out_dir = resolve_inside(args.out_dir, root)
        expected_dir = (
            resolve_inside(args.expected_dir, root) if args.expected_dir else None
        )
        brain_context = load_brain_context(brain_path)
    except (OSError, ValueError) as error:
        parser.error(str(error))

    duplicates = duplicate_stems(transcripts)
    if duplicates:
        parser.error(
            "transcripts would overwrite each other's outputs: " + ", ".join(duplicates)
        )
    if expected_dir:
        missing = [
            path.name
            for path in transcripts
            if not (expected_dir / f"{path.stem}.expected.json").is_file()
        ]
        if missing:
            parser.error("no reference answer for: " + ", ".join(missing))

    try:
        provider = get_provider()
    except ProviderError as error:
        parser.error(str(error))

    try:
        key = run_comparison(
            transcripts, out_dir, provider, brain_context, random.Random()
        )
    except ProviderError as error:
        print(f"FAILED: {error}")
        return 1

    key_path = out_dir / "blinding_key.json"
    key_path.write_text(json.dumps(key, indent=2) + "\n", encoding="utf-8")
    write_run_metadata(out_dir, root, transcripts, brain_path, provider)
    print(f"Saved {len(key)} pairs to {out_dir / 'blinded'}")
    print(f"Blinding key: {key_path} (do not open until scoring is final)")
    if expected_dir:
        print(f"Automated checks: {write_auto_scores(out_dir, key, expected_dir)}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
