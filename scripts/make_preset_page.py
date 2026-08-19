#!/usr/bin/env python3
"""Generate the paste-ready copy page for the OpenRouter preset.

WHY THIS EXISTS AS A SCRIPT RATHER THAN AS ONE-OFF WORK.

The compiled protocol is ~117,000 characters and it has to reach a textarea in the OpenRouter
dashboard by hand. Every route to getting it there has a way of failing silently:

* the repo is private, so a raw GitHub link asks the operator to be signed in;
* a chat attachment is awkward to select in full;
* a dashboard editor can truncate a paste this size without saying so;
* and Omi CANNOT READ THE REMOTE PRESET BACK to check. `master_prompt_hash` on the trace is what the
  repo EXPECTS the preset to hold, computed locally, so it reports the new hash whether or not the
  paste ever happened. Checking it proves nothing about the dashboard.

So the page carries its own verification: a marker string that exists in this version and no earlier
one. Search the saved preset field for it. That is the only check available, and it catches both
"pasted the wrong document" and "editor truncated it".

USAGE

    python scripts/make_preset_page.py [--out PATH] [--marker "SOME STRING"]

Then publish the file as an Artifact. **Pass the existing artifact URL as `url=` so it updates in
place rather than minting a second link** (see CLAUDE.md, "The preset goes out as a copy page").

The marker defaults to the newest distinctive heading the generator can find, but pick it
deliberately when you know which line is new in this version.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "apps" / "api"))

#: Strings that identify a protocol version, newest first. Add the new one at the TOP when a version
#: introduces a distinctive heading, and the page will name it as the check to run after pasting.
VERSION_MARKERS = (
    "USE THE WHOLE SCALE",          # v14: the dimension scale anchored to a number
    "THE 50 TO 74 INDICATORS",      # v13: the elevated band got its own list
    "A CLEAN ACCOUNT IS A FINDING",  # v12
)

_PAGE = """<title>Omi Master Analyst Protocol</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@800&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500;700&display=swap">
<style>
  :root{{--ground:#f6f7f9;--panel:#fff;--panel-2:#f0f2f6;--hair:#dde1e9;--hair-hard:#c6ccd8;
        --fg:#12151b;--fg-dim:#58606f;--fg-faint:#838c9c;--blue:#2f6fe0;--blue-soft:#e7effc;--ok:#2f8f47}}
  @media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{
        --ground:#08090c;--panel:#101319;--panel-2:#161a22;--hair:#1e242e;--hair-hard:#2c3542;
        --fg:#e6e9ef;--fg-dim:#99a2b2;--fg-faint:#6d7686;--blue:#5b9dff;--blue-soft:#12203a;--ok:#3fb950}}}}
  :root[data-theme="dark"]{{--ground:#08090c;--panel:#101319;--panel-2:#161a22;--hair:#1e242e;
        --hair-hard:#2c3542;--fg:#e6e9ef;--fg-dim:#99a2b2;--fg-faint:#6d7686;--blue:#5b9dff;
        --blue-soft:#12203a;--ok:#3fb950}}
  *{{box-sizing:border-box}}
  body{{background:var(--ground);color:var(--fg);margin:0;padding:0 20px 60px;
       font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.6;
       -webkit-font-smoothing:antialiased}}
  .wrap{{max-width:900px;margin:0 auto}}
  h1{{font-family:Archivo,Inter,sans-serif;font-weight:800;font-size:clamp(26px,4.4vw,38px);
     line-height:1.08;letter-spacing:-.02em;margin:0}}
  p{{margin:0;max-width:68ch}}
  .meta{{font-family:"JetBrains Mono",ui-monospace,monospace;font-size:10px;font-weight:500;
        letter-spacing:.17em;text-transform:uppercase;color:var(--fg-faint)}}
  code{{font-family:"JetBrains Mono",ui-monospace,monospace;font-size:.85em;background:var(--panel-2);
       border:1px solid var(--hair);border-radius:3px;padding:.08em .34em;word-break:break-word}}
  header{{padding:56px 0 22px;border-bottom:1px solid var(--hair-hard);
         display:flex;flex-direction:column;gap:14px}}
  .kick{{display:flex;align-items:center;gap:10px;flex-wrap:wrap}}
  .kick .tick{{width:9px;height:9px;background:var(--blue);flex:none}}
  .strip{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));border:1px solid var(--hair);
         border-radius:3px;background:var(--panel);overflow:hidden;margin-top:8px}}
  .ro{{padding:13px 15px;border-right:1px solid var(--hair);display:flex;flex-direction:column;gap:4px}}
  .ro:last-child{{border-right:0}}
  .ro .v{{font-family:"JetBrains Mono",monospace;font-size:15px;font-weight:700;letter-spacing:-.02em;
         font-variant-numeric:tabular-nums;word-break:break-all}}
  .bar{{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:26px 0 12px}}
  button{{font:600 14px/1 Inter,sans-serif;color:#fff;background:var(--blue);border:0;border-radius:3px;
         padding:12px 20px;cursor:pointer;transition:transform .12s cubic-bezier(.23,1,.32,1),opacity .12s}}
  button:hover{{opacity:.9}} button:active{{transform:scale(.98)}}
  button:focus-visible{{outline:2px solid var(--fg);outline-offset:2px}}
  #said{{font-family:"JetBrains Mono",monospace;font-size:12px;color:var(--ok);opacity:0;transition:opacity .2s}}
  #said.on{{opacity:1}}
  textarea{{width:100%;height:60vh;min-height:340px;background:var(--panel);color:var(--fg-dim);
           border:1px solid var(--hair);border-radius:3px;padding:14px;resize:vertical;
           font-family:"JetBrains Mono",ui-monospace,monospace;font-size:11.5px;line-height:1.55;
           white-space:pre;overflow:auto}}
  .note{{border-left:2px solid var(--blue);background:var(--blue-soft);padding:11px 14px;
        border-radius:0 3px 3px 0;margin-top:22px;font-size:14.5px}}
  ul{{margin:8px 0 0;padding-left:18px;color:var(--fg-dim);font-size:14.5px}}
  li{{margin-bottom:5px}}
  @media (prefers-reduced-motion:reduce){{*{{transition:none!important}}}}
</style>
<div class="wrap">
<header>
  <div class="kick"><span class="tick"></span><span class="meta">Omi Analyst &middot; OpenRouter preset</span></div>
  <h1>Omi Master Analyst Protocol</h1>
  <p style="color:var(--fg-dim)">Paste this whole document into the preset's system-prompt field, replacing everything already there.</p>
  <div class="strip">
    <div class="ro"><span class="meta">Hash</span><span class="v">{hash}</span></div>
    <div class="ro"><span class="meta">Characters</span><span class="v">{chars}</span></div>
    <div class="ro"><span class="meta">Generated</span><span class="v">{stamp}</span></div>
  </div>
</header>

<div class="bar">
  <button id="copy" type="button">Copy the whole protocol</button>
  <span id="said" role="status" aria-live="polite"></span>
</div>

<textarea id="src" readonly spellcheck="false" aria-label="Omi Master Analyst Protocol">{body}</textarea>

<div class="note">
  <strong>Check the paste took.</strong> After saving, search the preset field for
  <code>{marker}</code>. That string exists in this version and in no earlier one, so it tells you both
  that you pasted the right document and that the editor did not truncate it. Omi cannot read the
  remote preset back, so this is the only verification available: the hash on the trace is what the
  repo EXPECTS the preset to hold and reports the new value whether or not you ever pasted.
  <ul>
    <li>Confirm the preset still names a model. <code>OMI_OPENROUTER_MODEL</code> is empty by design, so the dashboard is the only source; a preset with no model resolves to nothing and floors every scan.</li>
    <li>If the copy button is blocked, click inside the box and press Ctrl+A then Ctrl+C (Cmd on Mac).</li>
  </ul>
</div>
</div>

<script>
  var btn = document.getElementById('copy'),
      src = document.getElementById('src'),
      said = document.getElementById('said');
  function flash(msg, ok) {{
    said.textContent = msg;
    said.style.color = ok ? 'var(--ok)' : 'var(--fg-faint)';
    said.classList.add('on');
    setTimeout(function () {{ said.classList.remove('on'); }}, 2600);
  }}
  btn.addEventListener('click', function () {{
    var text = src.value;
    function legacy() {{
      src.focus(); src.select(); src.setSelectionRange(0, text.length);
      var ok = false;
      try {{ ok = document.execCommand('copy'); }} catch (e) {{ ok = false; }}
      flash(ok ? 'Copied {chars} characters' : 'Selected. Press Ctrl+C or Cmd+C', ok);
    }}
    if (navigator.clipboard && navigator.clipboard.writeText) {{
      navigator.clipboard.writeText(text)
        .then(function () {{ flash('Copied {chars} characters', true); }})
        .catch(legacy);
    }} else {{ legacy(); }}
  }});
</script>
"""


def build(marker: str | None = None) -> tuple[str, dict]:
    """Return the page HTML and the protocol identity it was built from."""
    from app.reasoning.prompts.export import MASTER_PRESET_PATH, master_preset_matches_committed
    from app.reasoning.prompts.master_protocol import compile_master_analyst_protocol

    p = compile_master_analyst_protocol()
    text = p["text"]

    # The committed artifact is the thing an operator is told to trust, so refuse to build a page
    # from a compile that disagrees with it. Regenerate with write_master_preset() first.
    if not master_preset_matches_committed():
        raise SystemExit(
            f"{MASTER_PRESET_PATH} is stale against the current compile. Run "
            "app.reasoning.prompts.export.write_master_preset() first."
        )

    if marker is None:
        marker = next((m for m in VERSION_MARKERS if m in text), None)
        if marker is None:
            raise SystemExit(
                "No known version marker found in the compiled protocol. Add this version's "
                "distinctive heading to VERSION_MARKERS, newest first."
            )
    elif marker not in text:
        raise SystemExit(f"marker {marker!r} is not in the compiled protocol")

    # Only & and < need escaping for a faithful round-trip out of a textarea.
    body = text.replace("&", "&amp;").replace("<", "&lt;")
    if "</textarea" in body.lower():
        raise SystemExit("protocol contains a literal </textarea and would break the page")

    from datetime import date

    html = _PAGE.format(hash=p["hash"], chars=f"{len(text):,}", stamp=date.today().isoformat(),
                        marker=marker, body=body)

    # Prove what the reader copies is byte-identical to what the repo compiles.
    m = re.search(r"<textarea[^>]*>(.*)</textarea>", html, re.DOTALL)
    assert m and m.group(1).replace("&lt;", "<").replace("&amp;", "&") == text, "round-trip failed"

    return html, {"hash": p["hash"], "chars": len(text), "marker": marker}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=Path("preset-copy-page.html"))
    ap.add_argument("--marker", default=None,
                    help="string to tell the operator to search for after pasting")
    args = ap.parse_args()

    html, ident = build(args.marker)
    args.out.write_text(html, encoding="utf-8")
    print(f"wrote {args.out}")
    print(f"  hash   : {ident['hash']}")
    print(f"  chars  : {ident['chars']:,}")
    print(f"  marker : {ident['marker']}")
    print("\nPublish it as an Artifact, passing the EXISTING artifact url= so it updates in place.")
    print("See CLAUDE.md, 'The preset goes out as a copy page'.")


if __name__ == "__main__":
    main()
