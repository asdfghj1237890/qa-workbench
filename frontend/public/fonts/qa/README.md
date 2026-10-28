# QA interface fonts

These locally served WOFF2 files are UI glyph subsets of the Google Fonts Noto Traditional Chinese variable families and IBM Plex Mono:

| Bundled file | Official upstream font | Bundled license |
| --- | --- | --- |
| `qa-serif-ui.woff2` | [Noto Serif TC](https://raw.githubusercontent.com/google/fonts/main/ofl/notoseriftc/NotoSerifTC%5Bwght%5D.ttf) | [OFL-Noto-Serif-TC.txt](OFL-Noto-Serif-TC.txt) |
| `qa-sans-ui.woff2` | [Noto Sans TC](https://raw.githubusercontent.com/google/fonts/main/ofl/notosanstc/NotoSansTC%5Bwght%5D.ttf) | [OFL-Noto-Sans-TC.txt](OFL-Noto-Sans-TC.txt) |
| `qa-mono-400.woff2` | [IBM Plex Mono Regular](https://raw.githubusercontent.com/google/fonts/main/ofl/ibmplexmono/IBMPlexMono-Regular.ttf) | [OFL-IBM-Plex-Mono.txt](OFL-IBM-Plex-Mono.txt) |
| `qa-mono-500.woff2` | [IBM Plex Mono Medium](https://raw.githubusercontent.com/google/fonts/main/ofl/ibmplexmono/IBMPlexMono-Medium.ttf) | [OFL-IBM-Plex-Mono.txt](OFL-IBM-Plex-Mono.txt) |
| `qa-mono-600.woff2` | [IBM Plex Mono SemiBold](https://raw.githubusercontent.com/google/fonts/main/ofl/ibmplexmono/IBMPlexMono-SemiBold.ttf) | [OFL-IBM-Plex-Mono.txt](OFL-IBM-Plex-Mono.txt) |

All three families are distributed under the **SIL Open Font License 1.1**. The complete copyright notices and license terms are retained in the accompanying files, copied from the official [Serif license](https://raw.githubusercontent.com/google/fonts/main/ofl/notoseriftc/OFL.txt), [Sans license](https://raw.githubusercontent.com/google/fonts/main/ofl/notosanstc/OFL.txt) and [Mono license](https://raw.githubusercontent.com/google/fonts/main/ofl/ibmplexmono/OFL.txt).

The Noto subsets were generated with FontTools (`fonttools[woff]`) from printable ASCII, the interface strings in `src/i18n/*.json`, and supplementary QA interface copy. They retain the relevant layout features and variable weight data, and are not complete CJK fonts. Regenerate the subsets when interface copy introduces characters that are not yet included. The three static IBM Plex Mono weights contain printable ASCII for model identifiers, code, logs and metrics; non-ASCII text falls back to the local QA Sans family.

`src/css/qa-fonts.css` registers `NewsCout QA Serif`, `NewsCout QA Sans` and `NewsCout QA Mono` with `font-display: swap`. Missing glyphs and loading failures use the declared fallbacks: `Noto Serif TC`, then generic `serif`; or `Noto Sans TC`, `system-ui`, then generic `sans-serif`; or local QA Sans followed by generic `monospace`. The shared app still includes its existing Google Fonts stylesheet for other routes. QA interface text uses these local faces first; arbitrary model answers and news content outside the UI subsets can still use browser/OS fallback glyphs.

The three families were selected to provide consistent local rendering for the QA interface. The source design images do not establish their original font families, so these assets are not evidence that the designs used the same fonts.
