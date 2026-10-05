# Startup and Disney title verification — 2026-10-04

## Exact candidates

- Max 0.2.25: SHA-256 `f47e5772c48323d643ef819927be7b1bf203e9f2c9b2b064663b7ae368ba5875`.
- Disney 0.1.45: SHA-256 `8c7e8614729ff1793cdd1a7b1efa0b9680ba5ff3c4cd2af6e79fc37b4d6e6a66`.
- Installed from these ZIPs; all packaged files matched the installation byte for byte before testing. Kodi Windows 21.3 Omega, Python 3.8.15.

## Confirmed mechanisms and fixes

- Root directory launch previously handed off to a second Python invocation. It now finishes the directory request and continues in the same execution; black startup base precedes SlyGuy imports and profile requests.
- Owned root window favorites can open a plugin directory. Only an unambiguous root favorite of these add-ons is converted to the existing direct script entry, preserving label and thumbnail with a backup and rollback. Deep links and unrelated favorites are unchanged.
- Disney title rendering previously cleared its texture, checked the texture filename as a readiness signal, and restarted an animation per selection. Direct selected-card property binding now replaces that sequence. A missing logo uses the current title as text; unchanged selection does not reassign it.
- Settings surfaced an existing native-dialog error because neither add-on exposes settings.xml. The menu now reuses existing SlyGuy setting categories and their actions, over Clean UI. No setting values were changed during verification.

## Actual native Windows observations

Desktop inputs and screenshots were performed with the Windows computer-use tool, not Kodi mocks. Final-package cycles are separate from earlier candidate investigations.

| Cycle | Max | Disney |
| --- | --- | --- |
| 1 | Series, ficha, explicit episode playback, stop/return; settings and return; exit | Settings/categories and return; movie ficha, explicit playback, stop/return; exit |
| 2 | Search, result ficha, explicit movie playback, stop/return; exit | Avengers → Toy Story → 11-S title changes, then another rail; exit |
| 3 | Mi lista and return; exit | Series, inline episodes, season change, episode playback, stop with season preserved; return and exit |
| 4 | Películas, return and exit | Mi lista, return and exit |
| 5 | HBO, return and exit | Search, results and return; exit |
| 6 | Niños y Familia, return and exit | Películas, return and exit |
| 7 | Cancel profile picker; return to caller | Cancel profile picker; return to caller |
| 8 | Cancel intro, then wait beyond its end: no late picker | Cancel intro, then wait beyond its end: no late picker |
| 9 | Reopen, move profile focus without selecting, cancel | Reopen, move profile focus without selecting, cancel |
| 10 | Reopen, home, exit | Reopen, home, exit |

Ten open/close or cancelled-open cycles per add-on were completed; these are not ten playback sessions per add-on. Observed final-package transitions did not reveal the internal videos directory, require an extra Back at exit, cover the video with Clean UI, or leave a persistent black screen. Movie and episode video were visually confirmed for both. Settings, search and list returned to Clean UI.

Consecutive startup observations showed caller → black (approximately 0.6 seconds) → intro → profiles. Normal intros reached their natural end. Cold profile preparation sometimes required additional black time after the intro, as intended. Native logs show H.264 and AAC intro decoders and natural exits around 6.2 seconds. Intro MP4s are byte-identical to the preceding releases; their audio was not removed. Speaker output cannot be independently heard through the screenshot tool.

Disney metadata and logo matched the selected card at short snapshots (about 120 ms in the exercised warm-cache sequence). No previous-title persistence or repeated text/image alternation was observed in that sequence or across rails. Uncached remote images can still take time to arrive; they are not predownloaded or duplicated in a parallel cache. These observations are not a frame-by-frame recording or a controlled comparative benchmark.

The final Windows log contained no Python exception lines or intro-unavailable/timeout/cleanup warnings. Automated gates: 159 passed, 1 skipped across the Max suite and focused shared regressions. The portable repository copies of the added tests also ran successfully.

## Preservation and limits

- Authentication/API, plugin resolution, constants and settings modules are byte-identical to the preceding packaged versions. Existing graphics, sizes and MP4 resources are preserved. No skin-global changes, permanent services, credential/cache deletion, DRM/audio/buffer changes or new image downloader.
- A Disney direct favorite was exercised during the earlier candidate investigation; no matching Max favorite existed locally. Migration edge cases, owner cleanup, double activation, missing art and late-result rejection also have automated regressions; mocks are not native visual proof.
- A native resume prompt did not appear during these sessions. PIN-protected profile selection and logout were not exercised; credentials were preserved.
- No Chromecast HD G454V or theater AC3 test was performed here. Hardware performance, audio output and absence of intermittent long-playback freezes remain to be checked there with these same ZIPs. No two-hour playback or complete catalogue-pagination audit is claimed by this focused delivery.
