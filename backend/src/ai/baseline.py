"""Baseline agent script: transcript in, client profile out, raw reply saved.

Run from the repo root (needs OLLAMA_MODEL, and OLLAMA_BASE_URL if not localhost).
Paths must stay inside the directory you run it from:

    PYTHONPATH=backend python -m src.ai.baseline \
        tests/fixtures/baseline/transcript_1.txt --out-dir baseline_output
"""

import argparse
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from src.ai.baseline_prompt import build_baseline_client_profile_prompt
from src.ai.provider import ModelProvider, ModelResponse, ProviderError, get_provider


class BaselineOutputError(ValueError):
    """The model reply is not a client profile with name, needs and goals."""


@dataclass(frozen=True)
class BaselineResult:
    profile: dict
    response: ModelResponse
    raw_path: Path
    meta_path: Path


def parse_client_profile(text: str) -> dict:
    """Check a raw model reply has the baseline shape and return it as a dict."""
    try:
        profile = json.loads(text)
    except json.JSONDecodeError as error:
        raise BaselineOutputError(f"Reply is not valid JSON: {error}") from error
    if not isinstance(profile, dict):
        raise BaselineOutputError("Reply is not a JSON object")

    missing = {"name", "needs", "goals"} - profile.keys()
    if missing:
        raise BaselineOutputError(f"Reply is missing {sorted(missing)}")
    if profile["name"] is not None and not isinstance(profile["name"], str):
        raise BaselineOutputError("name must be a string or null")
    for field in ("needs", "goals"):
        values = profile[field]
        if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
            raise BaselineOutputError(f"{field} must be a list of strings")
    return profile


def run_baseline(
    transcript_path: Path,
    out_dir: Path,
    provider: ModelProvider,
    build_prompt: Callable[[str], str] = build_baseline_client_profile_prompt,
) -> BaselineResult:
    """Run the baseline prompt on one transcript and save the untouched reply.

    The raw reply is saved before it is checked, so a malformed answer is still
    kept for the Story 2.2 comparison. Story 2.2 passes its own build_prompt to
    run the Brain-assisted prompt through the same steps.
    """
    transcript = Path(transcript_path).read_text(encoding="utf-8")
    prompt = build_prompt(transcript)
    response = provider.generate(prompt, json_output=True)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(transcript_path).stem
    raw_path = out_dir / f"{stem}.raw.json"
    raw_path.write_text(response.text, encoding="utf-8")
    meta_path = out_dir / f"{stem}.meta.json"
    meta = {
        "transcript": Path(transcript_path).name,
        "provider": response.provider,
        "model": response.model,
        "duration_ms": response.duration_ms,
        # A functools.partial (the Brain-assisted prompt) keeps its function in .func.
        "prompt": getattr(build_prompt, "func", build_prompt).__name__,
    }
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    profile = parse_client_profile(response.text)
    return BaselineResult(profile, response, raw_path, meta_path)


def resolve_inside(path: Path, root: Path) -> Path:
    """Resolve path and refuse it if it points outside root (no ../ escapes)."""
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"{path} is outside {root}")
    return resolved


def duplicate_stems(paths: list[Path]) -> list[str]:
    """File names (without extension) shared by more than one path."""
    stems = [path.stem for path in paths]
    return sorted({stem for stem in stems if stems.count(stem) > 1})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("transcripts", nargs="+", type=Path)
    parser.add_argument("--out-dir", type=Path, default=Path("baseline_output"))
    args = parser.parse_args(argv)

    # Only read and write under the directory the script is run from (the repo).
    root = Path.cwd().resolve()
    try:
        transcripts = [resolve_inside(path, root) for path in args.transcripts]
        out_dir = resolve_inside(args.out_dir, root)
    except ValueError as error:
        parser.error(str(error))

    # Outputs are named after the transcript file, so a/t.txt and b/t.txt would
    # overwrite each other's saved results. Refuse before anything is written.
    duplicates = duplicate_stems(transcripts)
    if duplicates:
        parser.error(
            "transcripts would overwrite each other's outputs: " + ", ".join(duplicates)
        )

    try:
        provider = get_provider()
    except ProviderError as error:
        parser.error(str(error))

    failed = False
    for transcript in transcripts:
        try:
            result = run_baseline(transcript, out_dir, provider)
        except (ProviderError, BaselineOutputError) as error:
            print(f"{transcript}: FAILED ({error})")
            failed = True
            continue
        print(f"{transcript}: saved {result.raw_path}")
        print(json.dumps(result.profile, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
