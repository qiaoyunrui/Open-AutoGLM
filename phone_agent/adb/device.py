"""Device control utilities for Android automation."""

import re
import subprocess
import time
import xml.etree.ElementTree as ET

from phone_agent.config.apps import APP_PACKAGES
from phone_agent.config.timing import TIMING_CONFIG

_LAUNCHER_CACHE_TTL_SECONDS = 60.0
_UI_DUMP_PATH = "/sdcard/autoglm_window_dump.xml"


def _normalize_name(text: str) -> str:
    """Normalize an app/label name for fuzzy matching (case/dash/space-insensitive)."""
    return re.sub(r"[^a-z0-9\u3040-\u30ff\u4e00-\u9fff]", "", text.lower())


_APP_PACKAGES_NORMALIZED: dict[str, str] = {
    _normalize_name(name): package for name, package in APP_PACKAGES.items() if name
}

_launcher_packages_cache: dict[str | None, tuple[float, frozenset[str]]] = {}
_screen_size_cache: dict[str | None, tuple[float, tuple[int, int]]] = {}


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
    return None


def launch_app(
    app_name: str, device_id: str | None = None, delay: float | None = None
) -> bool:
    """
    Launch an app by name.

    Resolution is layered: the static ``APP_PACKAGES`` mapping first, then a
    fuzzy match against installed launchable packages on the device, and finally
    a uiautomator scan of the launcher that taps the icon whose on-screen label
    matches the requested name.

    Args:
        app_name: The app name or display label.
        device_id: Optional ADB device ID.
        delay: Delay in seconds after launching. If None, uses configured default.

    Returns:
        True if app was launched, False if the app could not be found.
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
    time.sleep(delay)
    return True


def _get_adb_prefix(device_id: str | None) -> list:
    """Get ADB command prefix with optional device specifier."""
    if device_id:
        return ["adb", "-s", device_id]
    return ["adb"]
