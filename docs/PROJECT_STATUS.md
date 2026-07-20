# Wallpaper Exporter Project Status

## V1 基线

V1 is the first publishable Windows 11 build of Wallpaper Exporter. It keeps original JPG/PNG bytes when exporting static snapshots, reads original Workshop titles, supports video frame selection, and avoids duplicate exports by SHA-256 content matching.

## Current UI behavior

- Startup defers the large Workshop scan until the Wallpaper library page is opened.
- The left navigation keeps the library progress and the `4K priority` note together at the bottom.
- `Desktop Global Hotkeys` is a separate page. It contains save, next, previous, and Steam project management actions, plus links to Settings and Update History.
- Settings stores the three global shortcuts and the automatic-save preference.

## Known boundaries

- Dynamic preview starts asynchronously and can take a moment to appear. This is expected Wallpaper Engine loading behavior and is not fully optimized yet.
- Steam does not expose a safe public Wallpaper Engine command for one-click unsubscribe. The management button opens the exact Workshop page so Steam can perform the authenticated unsubscribe action.
- A Scene/Web wallpaper may not produce a new `WallpaperEngineLockOverride.jpg` unless Wallpaper Engine's override snapshot feature is enabled. The program never fabricates a 4K image from a 2K snapshot.
- The current-page image is based on the newest valid primary Windows Themes snapshot. If Wallpaper Engine has not written a new snapshot, the displayed image cannot represent a newer rendered Scene frame without capturing or changing the desktop.

## Version rule

Publish the first accepted baseline as `V1`. Continue with `V2`, `V3`, and so on for later accepted releases. Keep the English repository name understandable to non-native English readers, for example `wallpaper-exporter`.
