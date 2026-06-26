"""Chrome launch flag presets and a merger that unions multi-value flags.

Chrome accepts ``--disable-features=A,B`` once. Pass it twice and only the
last wins. Stealth flags + mini flags + user-supplied flags can each carry
their own ``--disable-features``, so we union all of them before launch.
"""

from __future__ import annotations


def mini_flags() -> list[str]:
    """Chrome flags that cut RAM / CPU / disk per browser.

    Designed to be combined with :func:`funbrowser.stealth.stealth_flags`:
    does **not** turn off the GPU (stealth needs the real-GPU WebGL
    fingerprint), does **not** force ``--single-process`` (too crash-prone).
    What it does turn off:

    - site-per-process / IsolateOrigins → far fewer renderer processes
    - background timers, occluded windows, renderer backgrounding
    - extensions, sync, translate, breakpad, component-update
    - audio output, metrics, domain reliability, hang monitor
    - small disk / media caches, capped V8 heap per renderer

    Typical effect on a 10-browser farm: ~50-60% lower RSS vs default
    headless Chrome.
    """
    return [
        "--mute-audio",
        # Bundle all "feature off" toggles into a single --disable-features
        # so merge_flags doesn't have to fight with stealth_flags.
        "--disable-features="
        "IsolateOrigins,site-per-process,"
        "BackForwardCache,InterestFeedV2,"
        "GlobalMediaControls,CalculateNativeWinOcclusion,"
        "AudioServiceOutOfProcess",
        "--disable-background-networking",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "--disable-breakpad",
        "--disable-client-side-phishing-detection",
        "--disable-component-update",
        "--disable-domain-reliability",
        "--disable-hang-monitor",
        "--disable-ipc-flooding-protection",
        "--disable-popup-blocking",
        "--disable-prompt-on-repost",
        "--disable-sync",
        "--disable-translate",
        "--disable-extensions",
        "--disable-component-extensions-with-background-pages",
        "--disk-cache-size=10485760",
        "--media-cache-size=10485760",
        "--js-flags=--max-old-space-size=192",
        "--metrics-recording-only",
    ]


def nano_flags() -> list[str]:
    """Aggressive footprint cuts to layer on top of :func:`mini_flags`.

    Designed to push a single browser instance to its practical floor
    on Windows (~455 MB RSS, 7 processes) without breaking stealth or
    site loading. Three things:

    - ``--in-process-gpu`` — GPU code runs inside the browser process
      instead of a dedicated GPU process. Saves ~40 MB. The real-GPU
      WebGL fingerprint still works because GPU is not disabled, just
      moved in-process.
    - ``--renderer-process-limit=1`` — all tabs share one renderer.
      Saves another ~20 MB. **Disables site isolation** — fine for the
      typical farm pattern (1 browser = 1 account = 1 site) but unsafe
      if you mix unrelated origins in the same instance.
    - Extended ``--disable-features=`` that turns off the rest of
      Chrome's "phone home" surface (Translate, MediaRouter, the
      Privacy Sandbox / Topics API, optimisation hints, autofill
      server, certificate transparency component updater, etc.).
      Cheap, harmless, removes background work you don't want anyway.

    Pair with ``mini=True`` (or ``nano=True`` on :func:`Browser.start`
    implies it). On its own this list does not provide the cache /
    background / V8-heap tuning of mini_flags.
    """
    return [
        "--in-process-gpu",
        "--renderer-process-limit=1",
        "--disable-features="
        "Translate,MediaRouter,OptimizationHints,AcceptCHFrame,"
        "AutofillServerCommunication,CertificateTransparencyComponentUpdater,"
        "OptimizationHintsFetching,OptimizationTargetPrediction,"
        "InterestCohortAPI,PrivacySandboxSettings4,ImprovedCookieControls,"
        "LazyFrameLoading",
    ]


def merge_flags(*flag_lists: list[str]) -> list[str]:
    """Combine flag lists, unioning multi-value flags and deduplicating others.

    Chrome only honours the **last** ``--disable-features=`` argument on
    the command line. Without this merger, stealth_flags + mini_flags
    would silently drop one of their feature sets. We collect every
    feature mentioned across all lists and emit a single
    ``--disable-features=`` (same for ``--enable-features=``) at the end.
    """
    disabled: list[str] = []
    enabled: list[str] = []
    rest: list[str] = []
    seen: set[str] = set()

    for lst in flag_lists:
        for f in lst:
            if f.startswith("--disable-features="):
                disabled.extend(p for p in f.removeprefix("--disable-features=").split(",") if p)
            elif f.startswith("--enable-features="):
                enabled.extend(p for p in f.removeprefix("--enable-features=").split(",") if p)
            elif f not in seen:
                seen.add(f)
                rest.append(f)

    out: list[str] = list(rest)
    if disabled:
        out.append("--disable-features=" + ",".join(sorted(set(disabled))))
    if enabled:
        out.append("--enable-features=" + ",".join(sorted(set(enabled))))
    return out
