# Android build environment

The Android app builds against a standard Android SDK + the Gradle wrapper, plus the sibling
**Pulse** repo for the PULSE design system (`includeBuild("../../Pulse")` — Pulse must sit next
to Magpie, i.e. `<parent>/{Magpie,Pulse}`).

## Versions (from `gradle/libs.versions.toml` + `app/build.gradle.kts`)

| Tool | Version |
|---|---|
| JDK | 17 (source/target 17) |
| Gradle | 9.6.1 (the wrapper fetches it) |
| Android Gradle Plugin | 9.1.1 |
| Kotlin / KSP | 2.2.10 / 2.2.10-2.0.2 |
| Compose BOM | 2026.06.01 |
| compileSdk / targetSdk / minSdk | 37 / 35 / 26 |

## What you need installed

- **JDK 17** on the PATH.
- **Android SDK** with `platform-tools`, `platforms;android-37`, `build-tools;37.0.0`, and
  licenses accepted. Point Gradle at it via `android/local.properties` → `sdk.dir=<sdk path>`
  (gitignored; write it yourself or let the session-start hook do it).
- **Network egress** (for a fresh machine/CI/web session) to: `services.gradle.org` (Gradle
  distribution), `dl.google.com` + `maven.google.com` (SDK packages + AGP/Compose), and
  `repo1.maven.org` / `plugins.gradle.org` (mavenCentral + the plugin portal). Roborazzi pulls
  its Robolectric `android-all` runtime from mavenCentral too.

## Verify

```bash
cd android
./gradlew :app:testDebugUnitTest --no-daemon -PexcludeScreenshots   # unit tests (fast)
./gradlew :app:testDebugUnitTest                                     # includes Roborazzi
./gradlew :app:assembleDebug --no-daemon                             # the APK
./gradlew :app:recordRoborazziDebug                                  # (re)record screenshot baselines
```

CI (`.github/workflows/ci.yml`) mirrors this: GitHub's `ubuntu-latest` ships the SDK preinstalled,
so it just writes `local.properties=$ANDROID_HOME` and runs the tasks above.

## Claude Code on the web

`.claude/hooks/session-start.sh` bootstraps this automatically in a remote/web session (installs
the SDK, writes `local.properties`, warms the Gradle cache) **when the environment's network
policy allows the hosts above**. If it can't reach them it skips with a clear message and the
session still starts — open the network policy (Claude Code on the web environment settings,
https://code.claude.com/docs/en/claude-code-on-the-web) and restart the session.
