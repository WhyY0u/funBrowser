"""Chrome launch flags that defuse common headless/automation tells.

The base flags in _launcher already include --disable-blink-features=
AutomationControlled and --no-first-run; this module layers the rest of
the stealth set on top, plus the real-GPU flags needed to keep WebGL
from falling back to SwiftShader (which would re-fingerprint as headless).
"""

from __future__ import annotations


def stealth_flags() -> list[str]:
    return [
        # Block features that leak automation. WebRtcHideLocalIpsWithMdns is
        # what mDNS-obfuscates ICE candidates; disabling it together with the
        # IP-handling-policy flag below forces WebRTC traffic through the
        # configured proxy instead of leaking the real local IP.
        "--disable-features="
        "AutomationControlled,"
        "Translate,"
        "OptimizationHints,"
        "MediaRouter,"
        "DialMediaRouteProvider,"
        "AcceptCHFrame,"
        "AutoExpandDetailsElement,"
        "CertificateTransparencyComponentUpdater,"
        "AvoidUnnecessaryBeforeUnloadCheckSync,"
        "WebRtcHideLocalIpsWithMdns,"
        "Translate",
        # Keep IdleDetection enabled (some sites check that it exists)
        "--enable-features=NetworkService,NetworkServiceInProcess",
        # Force WebRTC traffic through the configured proxy. Without this,
        # ICE candidates leak the host's real IPv4/IPv6 even when stealth is
        # otherwise perfect.
        "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
        # Suppress background junk that screams "not a real user"
        "--disable-component-update",
        "--disable-background-networking",
        "--disable-default-apps",
        "--disable-domain-reliability",
        "--disable-sync",
        "--metrics-recording-only",
        "--no-default-browser-check",
        # Keep our keychain/password store inert (would otherwise prompt)
        "--password-store=basic",
        "--use-mock-keychain",
        # Real GPU for WebGL — without these, Chrome falls back to
        # SwiftShader which is a software renderer with a deterministic
        # fingerprint trivially identifying the browser as headless.
        "--use-gl=angle",
        "--use-angle=default",
        # Don't crash if GPU init fails — let the JS noise layer compensate.
        "--ignore-gpu-blocklist",
    ]
