# Captcha auto-solve

Pass a `funsolver.com` API key to `funbrowser.start` and detected
captchas solve themselves on every tab. No glue code required.

```python
async with await funbrowser.start(
    api_key="fs_xxx",
    auto_solve=True,   # default
) as browser:
    tab = await browser.get("https://protected-with-captcha.com")
    # if the page has a Turnstile / reCAPTCHA / hCaptcha widget, the
    # solver picks it up automatically and writes the token before
    # your next action.
    await tab.click("button[type=submit]")
```

## Supported types

| Captcha | Detector matches | Response field written |
|---|---|---|
| Cloudflare Turnstile | `.cf-turnstile[data-sitekey]` | `textarea[name="cf-turnstile-response"]` |
| reCAPTCHA v2 (+ Enterprise) | `.g-recaptcha[data-sitekey]` | every `g-recaptcha-response*` textarea |
| reCAPTCHA v3 (+ Enterprise) | hooks `window.grecaptcha.execute()` | returned to page-script `.then()` |
| hCaptcha | `.h-captcha[data-sitekey]` | `textarea[name="h-captcha-response"]` |
| FunCaptcha / Arkose | `[data-pkey]` | `input[name="fc-token"]` and aliases |
| GeeTest v3 + v4 | hooks `window.initGeetest` / `initGeetest4` | `geetest_challenge` / `_validate` / `_seccode` form fields, success callback invoked with the validated payload |

## Manual solve API

If you want to drive the solver from script code instead of relying on
the page-side detector:

```python
client = funbrowser.FunSolverClient("fs_xxx")
token = await client.solve_recaptcha_v2(
    sitekey="6Lc...",
    page_url="https://example.com",
    invisible=False,
)
# then write `token` into the textarea / trigger the callback yourself.
```

All methods are async. Each maps to its 2captcha / anti-captcha task
type (`RecaptchaV2TaskProxyless`, `HCaptchaTaskProxyless`, etc.). The
client polls until the task is `ready` and returns the token string.

## Custom integration

If the page's widget doesn't match the default detector selectors,
you can either:

1. **Add a data attribute** to the widget so our scanner finds it (the
   detectors use the documented attributes — `data-sitekey`,
   `data-pkey`, etc. — which most pages already have)
2. **Call `__funbrowser.solve()` from your own page JS**:

   ```js
   const token = await window.__funbrowser.solve({
     type: "recaptcha2",
     sitekey: "6Lc...",
     url: location.href,
     invisible: false,
   });
   ```

3. **Solve from Python** and inject yourself:

   ```python
   tok = await browser.solver_client.solve_hcaptcha(
       sitekey="...",
       page_url=tab.url,
   )
   await tab.evaluate(f"""
       document.querySelector('[name="h-captcha-response"]').value = {tok!r};
   """)
   ```

## Activity log

The local web panel (`pip install funbrowser[panel]`) shows every
captcha solve as it happens, with the captcha type, browser index, and
time taken. The panel also displays your live FunSolver balance.

## Endpoint configuration

If the real funsolver.com endpoints differ from the 2captcha-style
defaults the client assumes, override:

```python
await funbrowser.start(
    api_key="fs_xxx",
    solver_base_url="https://api.funsolver.com",  # default
)
```

Or subclass `FunSolverClient` and override `_post` / `_create_task` /
`_solve` for full control.
