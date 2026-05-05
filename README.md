# screenshot-translate

Translate the text inside screenshots into any language while keeping the
layout, fonts, colors, and visuals untouched. One CLI command, one OpenAI
API call per (image, language) pair, powered by the
[`gpt-image-2`](https://developers.openai.com/api/docs/models/gpt-image-2)
image-edit endpoint.

```
$ sst app.png --to spanish --to japanese --to "Brazilian Portuguese"
ok app.png -> app.es.png (412 KB, spanish)
ok app.png -> app.ja.png (398 KB, japanese)
ok app.png -> app.pt-br.png (415 KB, Brazilian Portuguese)
```

## Why

Localizing UI screenshots for docs, README files, marketing, App Store
listings, or release notes used to mean: re-launch the app in each locale,
take 50 screenshots, repeat for every release. `gpt-image-2` is good
enough at preserving layout and rendering text in many scripts that you
can do it from the original PNG. This tool is the thinnest CLI on top of
that.

## Install

Requires Python 3.9+.

```bash
pipx install screenshot-translate
# or
uv tool install screenshot-translate
# or, from source
git clone https://github.com/Reblexis/screenshot-translate.git
cd screenshot-translate
pip install .
```

You need an OpenAI API key with image-edit access:

```bash
export OPENAI_API_KEY=sk-...
```

The package installs two equivalent commands: `screenshot-translate` and
the shorter alias `sst`.

## Usage

### One image, one language

```bash
sst shot.png --to spanish
# writes shot.es.png next to shot.png
```

### One image, many languages

```bash
sst shot.png --to es,fr,ja,zh
# writes shot.es.png, shot.fr.png, shot.ja.png, shot.zh.png
```

### Many images, many languages

```bash
sst screenshots/*.png --to "Spanish,Japanese,Czech" --out-dir translated/
```

Outputs are named `<stem>.<lang-slug>.<ext>` (e.g. `home.ja.png`). For
language names not in the built-in slug table, a slug is derived from the
name itself (`"Brazilian Portuguese"` -> `brazilian-portuguese`).

### All options

```text
sst IMAGES... --to LANGUAGE [options]

  -t, --to TEXT            Target language. Repeat or comma-separate.
                           Accepts full names ("Spanish", "Brazilian
                           Portuguese") or codes ("es", "zh-cn").
  -o, --out-dir PATH       Output directory. Default: next to each source.
  -q, --quality CHOICE     low | medium | high | auto. Default: high.
  -s, --size TEXT          1024x1024, 1792x1024, 2048x2048, or "auto".
      --model TEXT         Default: gpt-image-2.
      --prompt-extra TEXT  Extra instruction appended to the prompt,
                           e.g. "Use formal register" or "Keep brand
                           name LookPilot in English".
  -j, --concurrency INT    Parallel API calls. Default: 4.
      --overwrite          Replace existing output files.
      --lang-subdirs       Write to <out-dir>/<lang>/<stem>.png instead of
                           <out-dir>/<stem>.<lang>.png. Cleaner for many
                           languages.
      --api-key TEXT       Defaults to $OPENAI_API_KEY.
  -V, --version
  -h, --help
```

### Recipes

Keep a brand name untranslated:

```bash
sst landing.png -t German --prompt-extra "Keep 'LookPilot' in English."
```

Cheap drafts first, then re-render the keepers:

```bash
sst hero.png -t es,fr,de,ja --quality low -o draft/
# review draft/, pick winners, then:
sst hero.png -t ja --quality high -o final/
```

Only generate what's missing:

```bash
sst screens/*.png -t en,es,fr,ja -o out/   # default skips existing
sst screens/*.png -t en,es,fr,ja -o out/ --overwrite   # force re-render
```

Use it as a library:

```python
from pathlib import Path
from screenshot_translate import translate_screenshot

translate_screenshot(
    source=Path("shot.png"),
    language="Czech",
    output=Path("shot.cs.png"),
    quality="high",
)
```

## How it works

For each (image, language) pair, the tool calls
`client.images.edit(model="gpt-image-2", image=..., prompt=...)` with a
prompt that asks the model to:

- translate every visible text element into the target language,
- preserve the original layout, fonts, colors, and visuals exactly,
- keep brand names, code, paths, URLs, and numbers unchanged,
- shorten gracefully when a translation overflows.

The response is a base64 PNG; it is decoded and written to disk. Source
files are never modified.

## Caveats

- **The model is stochastic.** Two runs of the same input can differ in
  small visual details. For reproducible output, run once and commit the
  result; do not regenerate on every build.
- **Layout is preserved, not pixel-perfect.** Anti-aliasing, padding, and
  one-off icons can shift slightly. For glossy marketing assets, use this
  as a starting point and touch up in Figma.
- **Long languages overflow.** German and Czech translations are often
  longer than English. The prompt asks for natural shortening, but if a
  button is tight, prefer `--prompt-extra "Abbreviate aggressively to
  fit"` or shrink the source string first.
- **Cost.** Each (image, language) pair is one `gpt-image-2` edit. Check
  current pricing on the OpenAI [pricing page](https://openai.com/api/pricing/)
  before running on hundreds of files.
- **Privacy.** Screenshots are uploaded to OpenAI. Do not run this on
  images containing secrets you would not paste into ChatGPT.

## Development

```bash
git clone https://github.com/Reblexis/screenshot-translate.git
cd screenshot-translate
pip install -e .
sst --help
```

PRs welcome. Keep dependencies minimal (`openai`, `click`, `rich`).

## License

MIT, see [LICENSE](LICENSE).
