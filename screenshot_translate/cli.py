"""CLI entry point: screenshot-translate (alias: sst)."""

from __future__ import annotations

import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable, List, Tuple

import click
from openai import OpenAI
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from . import __version__
from .core import (
    DEFAULT_MODEL,
    DEFAULT_QUALITY,
    DEFAULT_SIZE,
    translate_screenshot,
)


console = Console()


LANG_SLUG = {
    "english": "en", "spanish": "es", "french": "fr", "german": "de",
    "italian": "it", "portuguese": "pt", "brazilian portuguese": "pt-br",
    "european portuguese": "pt-pt", "dutch": "nl", "polish": "pl",
    "czech": "cs", "slovak": "sk", "russian": "ru", "ukrainian": "uk",
    "japanese": "ja", "korean": "ko", "chinese": "zh",
    "simplified chinese": "zh-cn", "traditional chinese": "zh-tw",
    "hindi": "hi", "bengali": "bn", "arabic": "ar", "hebrew": "he",
    "turkish": "tr", "vietnamese": "vi", "thai": "th", "indonesian": "id",
    "swedish": "sv", "norwegian": "no", "danish": "da", "finnish": "fi",
    "greek": "el", "romanian": "ro", "hungarian": "hu",
}


def language_slug(language: str) -> str:
    """Make a short filename-safe slug from a language name."""
    key = language.strip().lower()
    if key in LANG_SLUG:
        return LANG_SLUG[key]
    # Already a code (en, es, zh-cn) — keep as-is, slugified.
    return re.sub(r"[^a-z0-9-]+", "-", key).strip("-") or "lang"


def parse_languages(values: Iterable[str]) -> List[str]:
    out: List[str] = []
    for v in values:
        for piece in v.split(","):
            piece = piece.strip()
            if piece and piece not in out:
                out.append(piece)
    return out


def output_path(
    source: Path,
    language: str,
    out_dir: Path | None,
    lang_subdirs: bool = False,
) -> Path:
    slug = language_slug(language)
    base = out_dir if out_dir else source.parent
    # gpt-image-2 returns PNG bytes regardless of input format, so the
    # output is always .png even when the source is .jpg/.webp.
    if lang_subdirs:
        return base / slug / f"{source.stem}.png"
    return base / f"{source.stem}.{slug}.png"


@click.command(
    context_settings=dict(help_option_names=["-h", "--help"]),
    epilog=(
        "Examples:\n\n"
        "  sst shot.png --to spanish --to japanese\n"
        "  sst *.png --to es,fr,ja -o translated/\n"
        "  sst app.png -t \"Brazilian Portuguese\" -t Czech --quality high\n"
    ),
)
@click.argument(
    "images",
    nargs=-1,
    required=True,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=Path),
)
@click.option(
    "--to", "-t", "languages", multiple=True, required=True,
    help="Target language. Pass multiple times or comma-separated. "
         "Accepts full names ('Spanish', 'Brazilian Portuguese') or codes ('es').",
)
@click.option(
    "--out-dir", "-o", type=click.Path(file_okay=False, path_type=Path), default=None,
    help="Where to write outputs. Defaults to next to each source image.",
)
@click.option(
    "--quality", "-q",
    type=click.Choice(["low", "medium", "high", "auto"], case_sensitive=False),
    default=DEFAULT_QUALITY, show_default=True,
    help="gpt-image-2 quality tier.",
)
@click.option(
    "--size", "-s", default=DEFAULT_SIZE, show_default=True,
    help="Output size, e.g. 1024x1024, 1792x1024, 2048x2048, or 'auto'.",
)
@click.option(
    "--model", default=DEFAULT_MODEL, show_default=True,
    help="OpenAI image-edit model.",
)
@click.option(
    "--prompt-extra", default=None,
    help="Extra instruction appended to the translation prompt "
         "(e.g. 'Use formal register' or 'Keep brand name LookPilot in English').",
)
@click.option(
    "--concurrency", "-j", type=int, default=4, show_default=True,
    help="Number of parallel API calls.",
)
@click.option(
    "--overwrite/--no-overwrite", default=False,
    help="Replace existing output files instead of skipping them.",
)
@click.option(
    "--lang-subdirs/--no-lang-subdirs", default=False,
    help="Write outputs to <out-dir>/<lang>/<stem>.png instead of "
         "<out-dir>/<stem>.<lang>.png. Cleaner for many languages.",
)
@click.option(
    "--api-key", envvar="OPENAI_API_KEY", default=None,
    help="OpenAI API key. Defaults to $OPENAI_API_KEY.",
)
@click.version_option(__version__, "-V", "--version")
def main(
    images: Tuple[Path, ...],
    languages: Tuple[str, ...],
    out_dir: Path | None,
    quality: str,
    size: str,
    model: str,
    prompt_extra: str | None,
    concurrency: int,
    overwrite: bool,
    lang_subdirs: bool,
    api_key: str | None,
):
    """Translate text inside screenshots to other languages with gpt-image-2.

    Each (image, language) pair is one API call; outputs land next to the
    source as <name>.<lang>.<ext> unless --out-dir is given.
    """
    if not api_key and not os.environ.get("OPENAI_API_KEY"):
        console.print(
            "[red]No OpenAI API key found.[/red] "
            "Set OPENAI_API_KEY or pass --api-key."
        )
        sys.exit(2)

    langs = parse_languages(languages)
    client = OpenAI(api_key=api_key) if api_key else OpenAI()

    jobs: List[Tuple[Path, str, Path]] = []
    skipped = 0
    for img in images:
        for lang in langs:
            target = output_path(img, lang, out_dir, lang_subdirs=lang_subdirs)
            if target.exists() and not overwrite:
                console.print(f"[yellow]skip[/yellow] {target} (exists)")
                skipped += 1
                continue
            jobs.append((img, lang, target))

    if not jobs:
        console.print("Nothing to do.")
        sys.exit(0)

    console.print(
        f"[bold]screenshot-translate[/bold] {len(jobs)} job(s) "
        f"({len(images)} image(s) x {len(langs)} language(s)"
        + (f", {skipped} skipped" if skipped else "")
        + f"), model={model}, quality={quality}, size={size}, j={concurrency}"
    )

    failures: List[Tuple[Path, str, Exception]] = []
    successes = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task_id = progress.add_task("translating", total=len(jobs))
        with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
            futures = {
                pool.submit(
                    translate_screenshot,
                    src, lang, dst,
                    client=client,
                    model=model,
                    quality=quality,
                    size=size,
                    prompt_extra=prompt_extra,
                ): (src, lang, dst)
                for (src, lang, dst) in jobs
            }
            for fut in as_completed(futures):
                src, lang, dst = futures[fut]
                try:
                    result = fut.result()
                    successes += 1
                    progress.console.print(
                        f"[green]ok[/green] {result.source.name} -> "
                        f"{result.output} ({result.bytes_written // 1024} KB, {lang})"
                    )
                except Exception as exc:
                    failures.append((src, lang, exc))
                    progress.console.print(
                        f"[red]fail[/red] {src.name} -> {lang}: {exc}"
                    )
                progress.advance(task_id)

    console.print(
        f"\nDone: [green]{successes} ok[/green]"
        + (f", [red]{len(failures)} failed[/red]" if failures else "")
    )
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
