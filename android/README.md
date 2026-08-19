# FieldCheck AI — Android app

A native Kotlin + Jetpack Compose app for capturing field inspection photos on-device and submitting them to the FieldCheck AI backend (`../app`). See the main project [README.md](../README.md#android-app) for the full write-up; this file is a quick-reference for opening and building this module specifically.

## What's here

```
android/
├── app/
│   └── src/main/
│       ├── AndroidManifest.xml
│       ├── java/com/fieldcheck/ai/
│       │   ├── MainActivity.kt
│       │   ├── data/UserPreferences.kt        # DataStore: name/email session + backend URL
│       │   ├── network/                        # Retrofit API + response models
│       │   └── ui/
│       │       ├── FieldCheckNavHost.kt
│       │       ├── theme/
│       │       └── screens/
│       │           ├── LoginScreen.kt           # name + email, no password
│       │           ├── CaptureScreen.kt         # camera capture + upload
│       │           ├── ResultScreen.kt          # polls for AI results
│       │           ├── HistoryScreen.kt
│       │           └── SettingsScreen.kt        # backend URL config
│       └── res/
├── build.gradle.kts
├── settings.gradle.kts
└── gradle.properties
```

## Why there's no `.apk` in this delivery

Building an Android app requires the Android SDK plus Gradle/Maven dependency downloads from Google's and Gradle's servers. This project was authored in a sandboxed environment whose network allow-list doesn't include those domains, so the `.apk` genuinely could not be compiled there — this isn't a corner that was cut, it's a hard constraint of that environment. Everything else (all Kotlin source, the Gradle build config, the manifest) is real and complete; it just needs a normal internet-connected machine with Android Studio to compile.

## Quick start

1. Open this `android/` folder directly in Android Studio (`File → Open`).
2. Wait for Gradle sync to finish (first run downloads dependencies — needs internet).
3. Start the backend first, from the project root, bound to all interfaces so your phone can reach it:
   ```bash
   cd ..
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
4. Run the app (▶ in Android Studio) on an emulator or a phone connected via USB with developer mode / USB debugging on.
5. In the app: log in with any name + email, then in **Settings** set the backend URL:
   - Emulator → leave the default `http://10.0.2.2:8000`.
   - Real phone → your Mac's LAN IP, e.g. `http://192.168.1.42:8000` (same Wi-Fi network as the phone).
6. Tap the camera card on the **New Inspection** screen, take a photo, hit **Analyze Asset**.

## Notes

- No `gradlew`/`gradlew.bat`/`gradle-wrapper.jar` are included (see main README's Android section for why) — Android Studio's bundled Gradle handles this project directly.
- No app icon assets are bundled (`android:icon` is intentionally omitted from the manifest) — add one via `File → New → Image Asset` in Android Studio if you want a custom launcher icon before distributing a real build.
- This is a debug-oriented build (`usesCleartextTraffic="true"`, no release signing config) meant for pointing at your own local FieldCheck AI backend. Harden both before shipping to a public app store or a production HTTPS API.
