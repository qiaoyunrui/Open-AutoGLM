"""Device control utilities for Android automation."""

import glob
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from phone_agent.config.apps import APP_PACKAGES
from phone_agent.config.timing import TIMING_CONFIG

_LAUNCHER_CACHE_TTL_SECONDS = 60.0
_UI_DUMP_PATH = "/sdcard/autoglm_window_dump.xml"
_LABEL_SCAN_BUDGET_SECONDS = 60.0
_LABEL_SCAN_WORKERS = 8
_FOCUS_TIMEOUT_SECONDS = 15.0
_SYSTEM_PACKAGE_PREFIXES = (
    "android.",
    "com.android.",
    "com.google.android.",
    "com.samsung.android.",
    "com.sec.android.",
)


def _normalize_name(text: str) -> str:
    """Normalize an app/label name for fuzzy matching (case/dash/space-insensitive)."""
    return re.sub(r"[^a-z0-9\u3040-\u30ff\u4e00-\u9fff]", "", text.lower())


_APP_PACKAGES_NORMALIZED: dict[str, str] = {
    _normalize_name(name): package for name, package in APP_PACKAGES.items() if name
}

_launcher_packages_cache: dict[str | None, tuple[float, frozenset[str]]] = {}
_screen_size_cache: dict[str | None, tuple[float, tuple[int, int]]] = {}
_label_cache: dict[str | None, dict[str, frozenset[str]]] = {}


def get_current_app(device_id: str | None = None) -> str:
    """
    Get the currently focused app name.

    Args:
        device_id: Optional ADB device ID for multi-device setups.

    Returns:
        The app name if recognized, otherwise "System Home".
    """
    adb_prefix = _get_adb_prefix(device_id)

    result = subprocess.run(
        adb_prefix + ["shell", "dumpsys", "window"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    output = result.stdout
    if not output:
        raise ValueError("No output from dumpsys window")

    # Parse window focus info
    for line in output.split("\n"):
        if "mCurrentFocus" in line or "mFocusedApp" in line:
            for app_name, package in APP_PACKAGES.items():
                if package in line:
                    return app_name
            # Fall back to the raw package name for apps outside APP_PACKAGES.
            match = re.search(r"([a-zA-Z][\w.]*\.[\w.]+\.[\w.]+)", line)
            if match:
                return match.group(1)

    return "System Home"


def tap(
    x: int, y: int, device_id: str | None = None, delay: float | None = None
) -> None:
    """
    Tap at the specified coordinates.

    Args:
        x: X coordinate.
        y: Y coordinate.
        device_id: Optional ADB device ID.
        delay: Delay in seconds after tap. If None, uses configured default.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_tap_delay

    adb_prefix = _get_adb_prefix(device_id)

    subprocess.run(
        adb_prefix + ["shell", "input", "tap", str(x), str(y)], capture_output=True
    )
    time.sleep(delay)


def double_tap(
    x: int, y: int, device_id: str | None = None, delay: float | None = None
) -> None:
    """
    Double tap at the specified coordinates.

    Args:
        x: X coordinate.
        y: Y coordinate.
        device_id: Optional ADB device ID.
        delay: Delay in seconds after double tap. If None, uses configured default.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_double_tap_delay

    adb_prefix = _get_adb_prefix(device_id)

    subprocess.run(
        adb_prefix + ["shell", "input", "tap", str(x), str(y)], capture_output=True
    )
    time.sleep(TIMING_CONFIG.device.double_tap_interval)
    subprocess.run(
        adb_prefix + ["shell", "input", "tap", str(x), str(y)], capture_output=True
    )
    time.sleep(delay)


def long_press(
    x: int,
    y: int,
    duration_ms: int = 3000,
    device_id: str | None = None,
    delay: float | None = None,
) -> None:
    """
    Long press at the specified coordinates.

    Args:
        x: X coordinate.
        y: Y coordinate.
        duration_ms: Duration of press in milliseconds.
        device_id: Optional ADB device ID.
        delay: Delay in seconds after long press. If None, uses configured default.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_long_press_delay

    adb_prefix = _get_adb_prefix(device_id)

    subprocess.run(
        adb_prefix
        + ["shell", "input", "swipe", str(x), str(y), str(x), str(y), str(duration_ms)],
        capture_output=True,
    )
    time.sleep(delay)


def swipe(
    start_x: int,
    start_y: int,
    end_x: int,
    end_y: int,
    duration_ms: int | None = None,
    device_id: str | None = None,
    delay: float | None = None,
) -> None:
    """
    Swipe from start to end coordinates.

    Args:
        start_x: Starting X coordinate.
        start_y: Starting Y coordinate.
        end_x: Ending X coordinate.
        end_y: Ending Y coordinate.
        duration_ms: Duration of swipe in milliseconds (auto-calculated if None).
        device_id: Optional ADB device ID.
        delay: Delay in seconds after swipe. If None, uses configured default.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_swipe_delay

    adb_prefix = _get_adb_prefix(device_id)

    if duration_ms is None:
        # Calculate duration based on distance
        dist_sq = (start_x - end_x) ** 2 + (start_y - end_y) ** 2
        duration_ms = int(dist_sq / 1000)
        duration_ms = max(1000, min(duration_ms, 2000))  # Clamp between 1000-2000ms

    subprocess.run(
        adb_prefix
        + [
            "shell",
            "input",
            "swipe",
            str(start_x),
            str(start_y),
            str(end_x),
            str(end_y),
            str(duration_ms),
        ],
        capture_output=True,
    )
    time.sleep(delay)


def back(device_id: str | None = None, delay: float | None = None) -> None:
    """
    Press the back button.

    Args:
        device_id: Optional ADB device ID.
        delay: Delay in seconds after pressing back. If None, uses configured default.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_back_delay

    adb_prefix = _get_adb_prefix(device_id)

    subprocess.run(
        adb_prefix + ["shell", "input", "keyevent", "4"], capture_output=True
    )
    time.sleep(delay)


def home(device_id: str | None = None, delay: float | None = None) -> None:
    """
    Press the home button.

    Args:
        device_id: Optional ADB device ID.
        delay: Delay in seconds after pressing home. If None, uses configured default.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_home_delay

    adb_prefix = _get_adb_prefix(device_id)

    subprocess.run(
        adb_prefix + ["shell", "input", "keyevent", "KEYCODE_HOME"], capture_output=True
    )
    time.sleep(delay)


def _get_launcher_packages(device_id: str | None = None) -> frozenset[str]:
    """Return launchable package names, cached briefly per device."""
    now = time.time()
    cached = _launcher_packages_cache.get(device_id)
    if cached and now - cached[0] < _LAUNCHER_CACHE_TTL_SECONDS:
        return cached[1]

    adb_prefix = _get_adb_prefix(device_id)
    result = subprocess.run(
        adb_prefix
        + [
            "shell",
            "cmd",
            "package",
            "query-activities",
            "-a",
            "android.intent.action.MAIN",
            "-c",
            "android.intent.category.LAUNCHER",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    packages: set[str] = set()
    if result.stdout:
        packages = {
            m.group(1)
            for m in re.finditer(r"packageName=([^\s,)>\"]+)", result.stdout)
        }
    frozen = frozenset(packages)
    _launcher_packages_cache[device_id] = (now, frozen)
    return frozen


def _get_screen_size(device_id: str | None = None) -> tuple[int, int] | None:
    """Get the logical screen size, cached briefly per device."""
    now = time.time()
    cached = _screen_size_cache.get(device_id)
    if cached and now - cached[0] < _LAUNCHER_CACHE_TTL_SECONDS:
        return cached[1]

    result = subprocess.run(
        _get_adb_prefix(device_id) + ["shell", "wm", "size"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    match = re.search(r"(\d+)x(\d+)", result.stdout or "")
    if not match:
        return None
    size = int(match.group(1)), int(match.group(2))
    _screen_size_cache[device_id] = (now, size)
    return size


def _find_aapt() -> str | None:
    """Locate the Android SDK ``aapt`` binary on the host."""
    aapt = os.environ.get("ANDROID_AAPT") or shutil.which("aapt")
    if aapt:
        return aapt
    roots = [
        os.environ.get("ANDROID_HOME") or "",
        os.environ.get("ANDROID_SDK_ROOT") or "",
        str(Path.home() / "Android" / "Sdk"),
    ]
    for root in roots:
        if not root:
            continue
        for build_tools in sorted(
            glob.glob(os.path.join(root, "build-tools", "*")), reverse=True
        ):
            candidate = os.path.join(build_tools, "aapt")
            if os.path.isfile(candidate):
                return candidate
    return None


_LABEL_BADGING_RE = re.compile(
    r"^application-label(?:-[^:]+)?:'([^']*)'", re.MULTILINE
)


def _parse_badging_labels(badging: str) -> frozenset[str]:
    """Extract normalized display labels from ``aapt dump badging`` output."""
    return frozenset(
        normalized
        for match in _LABEL_BADGING_RE.finditer(badging)
        if (normalized := _normalize_name(match.group(1)))
    )


def _label_cache_path(device_id: str | None) -> Path:
    """Path of the on-disk label->package cache for a device."""
    base = os.environ.get("AUTOGLM_LABEL_CACHE_DIR") or tempfile.gettempdir()
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", device_id or "default")
    return Path(base) / f"autoglm_launcher_labels_{safe}.json"


def _load_label_cache(device_id: str | None) -> dict[str, frozenset[str]]:
    """Return the in-process label cache, backfilling from disk on first use."""
    cached = _label_cache.get(device_id)
    if cached is not None:
        return cached
    path = _label_cache_path(device_id)
    loaded: dict[str, frozenset[str]] = {}
    try:
        if path.is_file():
            loaded = {
                package: frozenset(labels)
                for package, labels in json.loads(path.read_text(encoding="utf-8")).items()
            }
    except (OSError, ValueError):
        loaded = {}
    _label_cache[device_id] = loaded
    return loaded


def _save_label_cache(device_id: str | None, cache: dict[str, frozenset[str]]) -> None:
    """Persist the in-process label cache to disk."""
    try:
        _label_cache_path(device_id).write_text(
            json.dumps(
                {package: list(labels) for package, labels in cache.items()},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except OSError:
        pass


def _apk_path_for(package: str, adb_prefix: list) -> str | None:
    """Return the on-device APK path for a package via ``pm path``."""
    result = subprocess.run(
        adb_prefix + ["shell", "pm", "path", package],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    match = re.search(r"package:(\S+)", result.stdout or "")
    return match.group(1) if match else None


def _dump_badging(apk_path: str, aapt: str) -> str:
    result = subprocess.run(
        [aapt, "dump", "badging", apk_path],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout or ""


def _scan_package_labels(package: str, adb_prefix: list, aapt: str) -> frozenset[str]:
    """Pull one APK and extract its normalized display labels (self-contained)."""
    apk_path = _apk_path_for(package, adb_prefix)
    if not apk_path:
        return frozenset()

    fd, tmp_path = tempfile.mkstemp(suffix=".apk", prefix="autoglm_label_")
    try:
        os.close(fd)
        pull = subprocess.run(
            adb_prefix + ["pull", apk_path, tmp_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if pull.returncode == 0 and os.path.getsize(tmp_path) > 0:
            return _parse_badging_labels(_dump_badging(tmp_path, aapt))
    except OSError:
        pass
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    return frozenset()


def _scan_labels_for_name(app_name: str, device_id: str | None) -> bool:
    """Learn display labels from installed APKs via host ``aapt``.

    Scans uncached packages in parallel within a wall-clock budget, prioritizing
    user-installed apps and skipping packages already resolvable by the static
    mapping. Results are persisted to disk so later calls pick up where the last
    one left off. Returns True once a package label matches the requested name.
    """
    aapt = _find_aapt()
    if not aapt:
        return False

    normalized = _normalize_name(app_name)
    cache = _load_label_cache(device_id)
    if any(normalized in labels for labels in cache.values()):
        return True

    static_packages = frozenset(_APP_PACKAGES_NORMALIZED.values())
    packages = sorted(
        package
        for package in _get_launcher_packages(device_id)
        if package not in static_packages and package not in cache
    )
    # Third-party apps first (most common launch targets), system apps last.
    packages.sort(
        key=lambda package: (
            package.startswith(_SYSTEM_PACKAGE_PREFIXES),
            package,
        )
    )

    budget = float(os.environ.get("AUTOGLM_LABEL_SCAN_BUDGET", _LABEL_SCAN_BUDGET_SECONDS))
    workers = min(
        int(os.environ.get("AUTOGLM_LABEL_SCAN_WORKERS", _LABEL_SCAN_WORKERS)),
        max(len(packages), 1),
    )
    adb_prefix = _get_adb_prefix(device_id)
    deadline = time.monotonic() + budget

    found = False
    executor = ThreadPoolExecutor(max_workers=workers)
    try:
        futures = {
            executor.submit(_scan_package_labels, package, adb_prefix, aapt): package
            for package in packages
        }
        for future in as_completed(futures):
            package = futures[future]
            try:
                cache[package] = future.result()
            except Exception:
                cache[package] = frozenset()
            if normalized in cache[package]:
                found = True
                break
            if time.monotonic() >= deadline:
                break
    finally:
        for future in futures:
            future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)

    _save_label_cache(device_id, cache)
    return found


def _package_matches(requested_norm: str, package: str) -> bool:
    """Return True if a normalized name matches a package path token."""
    for part in re.split(r"[.\-_:]", package.lower()):
        if part == requested_norm:
            return True
        if len(requested_norm) >= 4 and requested_norm in part:
            return True
    return False


def _bounds_center(bounds: str | None) -> tuple[int, int] | None:
    """Parse a uiautomator bounds string into its center point."""
    if not bounds:
        return None
    match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds.strip())
    if not match:
        return None
    x1, y1, x2, y2 = (int(value) for value in match.groups())
    return (x1 + x2) // 2, (y1 + y2) // 2


def _tap_label_in_dump(dump_xml: str, norm_label: str, adb_prefix: list) -> bool:
    """Tap the first screen node whose text/content-desc matches the normalized label."""
    try:
        root = ET.fromstring(dump_xml)
    except ET.ParseError:
        return False

    for node in root.iter():
        label = node.get("text") or node.get("content-desc") or ""
        if label and _normalize_name(label) == norm_label:
            center = _bounds_center(node.get("bounds"))
            if center is not None:
                x, y = center
                subprocess.run(
                    adb_prefix + ["shell", "input", "tap", str(x), str(y)],
                    capture_output=True,
                )
                time.sleep(TIMING_CONFIG.device.default_tap_delay)
                return True
    return False


def _tap_matching_screen_node(
    app_name: str, device_id: str | None = None, include_app_drawer: bool = True
) -> bool:
    """Last resort: scan the launcher UI for a label and tap its icon.

    Checks the home screen first; when ``include_app_drawer`` is set, retries
    once after a swipe-up so app-drawer items can be found as well.
    """
    adb_prefix = _get_adb_prefix(device_id)
    subprocess.run(
        adb_prefix + ["shell", "input", "keyevent", "KEYCODE_HOME"],
        capture_output=True,
    )
    time.sleep(TIMING_CONFIG.device.default_home_delay)

    norm_label = _normalize_name(app_name)
    attempts = 2 if include_app_drawer else 1
    for attempt in range(attempts):
        subprocess.run(
            adb_prefix + ["shell", "uiautomator", "dump", _UI_DUMP_PATH],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        dump = subprocess.run(
            adb_prefix + ["shell", "cat", _UI_DUMP_PATH],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if dump.stdout and _tap_label_in_dump(dump.stdout, norm_label, adb_prefix):
            return True

        if attempt + 1 < attempts:
            size = _get_screen_size(device_id)
            if not size:
                break
            width, height = size
            subprocess.run(
                adb_prefix
                + [
                    "shell",
                    "input",
                    "swipe",
                    str(width // 2),
                    str(int(height * 0.85)),
                    str(width // 2),
                    str(int(height * 0.4)),
                    "600",
                ],
                capture_output=True,
            )
            time.sleep(TIMING_CONFIG.device.default_swipe_delay)
    return False


def _resolve_package(app_name: str, device_id: str | None = None) -> str | None:
    """Best-effort resolution of an app name to an installed, launchable package."""
    exact = APP_PACKAGES.get(app_name)
    if exact:
        return exact

    normalized = _normalize_name(app_name)
    alias = _APP_PACKAGES_NORMALIZED.get(normalized)
    if alias:
        return alias

    launcher_packages = _get_launcher_packages(device_id)
    if "." in app_name and app_name.lower() in launcher_packages:
        return app_name.lower()
    for package in launcher_packages:
        if _package_matches(normalized, package):
            return package

    # Label-based resolution: learn display labels from installed APKs via aapt.
    if _scan_labels_for_name(app_name, device_id):
        for package, labels in _load_label_cache(device_id).items():
            if normalized in labels:
                return package
    return None


def _wait_for_package_focus(
    package: str, device_id: str | None, timeout: float
) -> bool:
    """Wait until an app package owns the focused window.

    Cold starts can take several seconds and pass through a focus-less
    transition (``mCurrentFocus=null``); report success only once the target
    actually holds the screen so callers never mistake pre-launch frames for
    the launched app. Only ``mCurrentFocus`` counts: ``mFocusedApp`` lines are
    unreliable here because stale ``AppWindowToken`` entries for the previous
    activity linger in the dump until focus settles.
    """
    adb_prefix = _get_adb_prefix(device_id)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            result = subprocess.run(
                adb_prefix + ["shell", "dumpsys", "window"],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
        except OSError:
            return False
        for line in result.stdout.split("\n"):
            if "mCurrentFocus=" in line and package in line:
                return True
        time.sleep(0.5)
    return False


def launch_app(
    app_name: str, device_id: str | None = None, delay: float | None = None
) -> bool:
    """
    Launch an app by name.

    Resolution is layered: the static ``APP_PACKAGES`` mapping first, then a
    fuzzy match against installed launchable packages on the device, then a
    ``aapt`` label scan of installed APKs, and finally a uiautomator scan of
    the launcher that taps the icon whose on-screen label matches the name.
    The resolved package must actually gain the foreground window within a
    timeout, otherwise the launch is reported as failed.

    Args:
        app_name: The app name or display label.
        device_id: Optional ADB device ID.
        delay: Delay in seconds after launching. If None, uses configured default.

    Returns:
        True if the app was launched and came to the foreground, False if it
        could not be found or never gained the foreground window.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_launch_delay

    package = _resolve_package(app_name, device_id)
    if package is None:
        return _tap_matching_screen_node(app_name, device_id, include_app_drawer=True)

    adb_prefix = _get_adb_prefix(device_id)

    subprocess.run(
        adb_prefix
        + [
            "shell",
            "monkey",
            "-p",
            package,
            "-c",
            "android.intent.category.LAUNCHER",
            "1",
        ],
        capture_output=True,
    )
    focus_timeout = float(
        os.environ.get("AUTOGLM_LAUNCH_FOCUS_TIMEOUT", _FOCUS_TIMEOUT_SECONDS)
    )
    if not _wait_for_package_focus(package, device_id, focus_timeout):
        return False
    time.sleep(delay)
    return True


def _get_adb_prefix(device_id: str | None) -> list:
    """Get ADB command prefix with optional device specifier."""
    if device_id:
        return ["adb", "-s", device_id]
    return ["adb"]
