"""
Enhancify APKMirror Scraper & Downloader Module
Handles scraping app version lists, tag detection ([RECOMMENDED], [INSTALLED], [STABLE], [BETA]),
caching in apps_meta/, download URL scraping, and downloading APK/APKM files.
"""

import concurrent.futures
import datetime
import json
import re
import shutil
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

from src.antisplit import ExtractedAppMeta, antisplit_mgr
from src.config import config
from src.environment import env
import threading
import time

from src.utils import DownloadResult, download_file, download_file_ex


USER_AGENT = "APKUpdater-3.0.3"
APKMIRROR_BASE = "https://www.apkmirror.com"
APP_EXISTS_URL = f"{APKMIRROR_BASE}/wp-json/apkm/v1/app_exists/"
APP_EXISTS_AUTH = "Basic YXBpLXRvb2xib3gtZm9yLWdvb2dsZS1wbGF5OkNiVVcgQVVMZyBNRVJXIHU4M3IgS0s0SCBEbmJL"
APP_EXISTS_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Authorization": APP_EXISTS_AUTH,
}

# Browser handoff: where Android browsers save downloads. APKMirror only serves
# .apk and .apkm.
BROWSER_DOWNLOAD_DIRS = (
    Path.home() / "storage" / "downloads",
    Path("/storage/emulated/0/Download"),
    Path("/sdcard/Download"),
)
_BROWSER_EXTS = (".apk", ".apkm")


class APKMirrorBlocked(Exception):
    """APKMirror answered with Cloudflare's managed JS challenge, which plain HTTP clients cannot pass."""


def _is_challenge(resp) -> bool:
    return resp.status_code == 403 and resp.headers.get("cf-mitigated", "").lower() == "challenge"



@dataclass
class ScrapedVersion:
    version: str
    tag: str  # e.g. "[STABLE]", "[BETA]", "[ALPHA]", "[RECOMMENDED]", "[INSTALLED]"
    url: str
    note: str = ""  # extra hint shown beside the version, e.g. "build 385811006"


def _version_sort_key(version: str) -> Tuple[Tuple[int, ...], str]:
    """Newest-first ordering key: dotted-numeric prefix as an int tuple,
    full version string as a deterministic tie-break."""
    nums = re.match(r"(\d+(?:\.\d+)*)", version)
    num_key = tuple(int(p) for p in nums.group(1).split(".")) if nums else (0,)
    return (num_key, version)


def order_versions(versions: List["ScrapedVersion"]) -> List["ScrapedVersion"]:
    """Order the version list for display: the newest (up to 3)
    [RECOMMENDED] versions first, then everything else newest→oldest.
    Recommended versions beyond the top 3 stay in the main body."""
    ordered = sorted(versions, key=lambda v: _version_sort_key(v.version), reverse=True)
    recommended = [v for v in ordered if v.tag == "[RECOMMENDED]"][:3]
    pinned = {id(v) for v in recommended}
    return recommended + [v for v in ordered if id(v) not in pinned]

class APKMirrorScraper:
    """Scrapes APKMirror for app versions and download links."""

    def __init__(self, workspace_dir: Optional[Path] = None):
        self.workspace_dir = workspace_dir or Path(__file__).resolve().parent.parent
        self.cache_dir = self.workspace_dir / "apps_meta"
        self.apps_dir = self.workspace_dir / "apps"
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.apps_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_file(self, app_name: str) -> Path:
        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", app_name)
        return self.cache_dir / f"{safe_name}_metadata.json"

    # --- Cache Manager ---

    def read_cached_versions(self, app_name: str, min_page_limit: int = 5) -> Optional[List[Dict[str, str]]]:
        """Read cached version list if valid."""
        cache_file = self._get_cache_file(app_name)
        if not cache_file.exists():
            return None

        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            cached_pages = data.get("page_limit", 0)
            if cached_pages < min_page_limit:
                return None
            versions = data.get("versions", [])
            if isinstance(versions, list) and versions:
                return versions
        except Exception:
            pass
        return None

    def write_cached_versions(self, app_name: str, versions: List[Dict[str, str]], page_limit: int = 5) -> None:
        """Write scraped versions to cache."""
        cache_file = self._get_cache_file(app_name)
        now_dt = datetime.date.today().strftime("%Y-%m-%d")
        data = {
            "app_name": app_name,
            "cached_at": now_dt,
            "page_limit": page_limit,
            "version_count": len(versions),
            "versions": versions,
        }
        try:
            cache_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def clear_cache(self, app_name: str) -> None:
        """Clear cache for a given app."""
        cache_file = self._get_cache_file(app_name)
        cache_file.unlink(missing_ok=True)

    # --- App resolution (real name + category slug from APKMirror) ---

    def resolve_apps_info(self, pkg_names: List[str], batch_size: int = 100) -> Dict[str, Dict[str, str]]:
        """Resolve the real APKMirror app name + uploads-page category slug for
        each package via the app_exists API (the same endpoint the classic
        bash flow used). APKMirror's slugs can't be guessed from the package
        name (e.g. com.twitter.android -> "twitter", com.instagram.android ->
        "instagram-instagram"), so guessing breaks the version scrape/download
        step for any package whose slug doesn't match its name.
        """
        result: Dict[str, Dict[str, str]] = {}
        headers = APP_EXISTS_HEADERS
        pkg_names = [p for p in pkg_names if p]

        for i in range(0, len(pkg_names), batch_size):
            batch = pkg_names[i:i + batch_size]
            try:
                r = requests.post(
                    APP_EXISTS_URL, headers=headers, json={"pnames": batch}, timeout=15
                )
                if r.status_code != 200:
                    continue
                for entry in r.json().get("data", []):
                    if not entry.get("exists"):
                        continue
                    pkg = entry.get("pname")
                    app = entry.get("app") or {}
                    link = app.get("link", "")
                    slug_match = re.search(r"/([^/]+)/$", link)
                    slug = slug_match.group(1) if slug_match else None
                    name = (app.get("name") or "").strip()
                    if pkg and slug and name:
                        result[pkg] = {"appName": name, "apkmirrorAppName": slug}
            except Exception:
                continue

        return result

    # --- Scraping ---

    def scrape_versions_page(self, apkmirror_app_name: str, page_num: int) -> List[Dict[str, str]]:
        """Scrape a single uploads page on APKMirror."""
        url = f"{APKMIRROR_BASE}/uploads/page/{page_num}/?appcategory={apkmirror_app_name}"
        headers = {"User-Agent": USER_AGENT}
        results = []

        try:
            r = requests.get(url, headers=headers, timeout=10)
            if _is_challenge(r):
                raise APKMirrorBlocked(url)
            if r.status_code != 200:
                return []

            soup = BeautifulSoup(r.text, "html.parser")
            rows = soup.select("div.widget_appmanager_recentpostswidget div.listWidget div:not([class])")
            if not rows:
                rows = soup.select("div.listWidget div.appRow")

            for row in rows:
                title_elem = row.select_one("a.fontBlack") or row.select_one("h5 a") or row.select_one("a")
                if not title_elem:
                    continue

                full_title = title_elem.get_text(strip=True)
                href = title_elem.get("href", "")
                if not href:
                    continue

                # Extract version
                ver_match = re.search(r"(\d+(?:\.\d+)+(?:-[a-zA-Z0-9\._]+)?)", full_title)
                version_str = ver_match.group(1) if ver_match else full_title

                tag = "[STABLE]"
                title_lower = full_title.lower()
                if "beta" in title_lower:
                    tag = "[BETA]"
                elif "alpha" in title_lower:
                    tag = "[ALPHA]"

                results.append({
                    "version": version_str,
                    "tag": tag,
                    "url": href,
                })
        except APKMirrorBlocked:
            raise
        except Exception:
            pass

        return results

    def fetch_versions_list(
        self,
        apkmirror_app_name: str,
        supported_versions: Optional[List[str]] = None,
        installed_version: str = "",
        force_refresh: bool = False,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> List[ScrapedVersion]:
        """
        Fetch version list for an app, either from cache or by scraping APKMirror.
        Tags versions with [RECOMMENDED] and [INSTALLED].
        """
        page_limit = config.get_apkmirror_page_limit()
        supported_versions = supported_versions or []

        raw_versions = None
        if not force_refresh:
            raw_versions = self.read_cached_versions(apkmirror_app_name, page_limit)

        if not raw_versions:
            if progress_callback:
                progress_callback(f"Scraping {page_limit} pages from APKMirror...")

            all_scraped = []
            blocked = False
            # Probe page 1 alone first: a Cloudflare challenge or rate limit then
            # costs one request instead of a burst across every page.
            all_scraped.extend(self.scrape_versions_page(apkmirror_app_name, 1))
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = {
                    executor.submit(self.scrape_versions_page, apkmirror_app_name, p): p
                    for p in range(2, page_limit + 1)
                }
                for fut in concurrent.futures.as_completed(futures):
                    try:
                        res = fut.result()
                        all_scraped.extend(res)
                    except APKMirrorBlocked:
                        blocked = True
                    except Exception:
                        pass

            # Deduplicate by version
            seen = set()
            raw_versions = []
            for item in all_scraped:
                v = item["version"]
                if v not in seen:
                    seen.add(v)
                    raw_versions.append(item)

            if raw_versions:
                self.write_cached_versions(apkmirror_app_name, raw_versions, page_limit)

        if not raw_versions:
            if blocked:
                raise APKMirrorBlocked(apkmirror_app_name)
            return []

        # Process tags
        processed: List[ScrapedVersion] = []
        for item in raw_versions:
            v = item.get("version", "")
            base_tag = item.get("tag", "[STABLE]")
            url = item.get("url", "")

            final_tag = base_tag
            if v in supported_versions:
                final_tag = "[RECOMMENDED]"
            elif installed_version and v == installed_version:
                final_tag = "[INSTALLED]"

            processed.append(ScrapedVersion(version=v, tag=final_tag, url=url))

        return order_versions(processed)

    # --- Scrape Download Link ---

    def scrape_download_link(self, version_url: str) -> Optional[Tuple[str, str, int, str]]:
        """
        Scrape download URL, file extension (apk/apkm), expected size, and download link.
        Returns (download_url, format_type, size_bytes, extension)
        Raises APKMirrorBlocked when the page is behind Cloudflare's challenge.
        """
        headers = {"User-Agent": USER_AGENT}
        full_url = version_url if version_url.startswith("http") else f"{APKMIRROR_BASE}{version_url}"

        try:
            # 1. Fetch release / version page
            r = requests.get(full_url, headers=headers, timeout=10)
            if _is_challenge(r):
                raise APKMirrorBlocked(full_url)
            if r.status_code != 200:
                return None

            soup = BeautifulSoup(r.text, "html.parser")

            # Check if direct download or variants table
            canonical = soup.select_one("link[rel='canonical']")
            canonical_href = canonical.get("href", "") if canonical else ""

            target_variant_url = ""
            app_format = "APK"
            app_ext = "apk"
            arch = env.get_arch()

            if "apk-download" in canonical_href:
                target_variant_url = canonical_href
            else:
                # Variant selection table
                table = soup.select_one("div.table-variants") or soup.select_one("div.variants-table")
                if not table:
                    # Look for download buttons directly
                    dl_btn = soup.select_one("a.accent_bg[href*='download']")
                    if dl_btn:
                        target_variant_url = urllib.parse.urljoin(APKMIRROR_BASE, dl_btn.get("href"))
                else:
                    prefer_split = config.is_on("PREFER_SPLIT_APK")
                    rows = table.select("div.table-row")
                    chosen_row = None

                    # Find matching architecture & type
                    for row in rows:
                        row_text = row.get_text().lower()
                        is_bundle = "bundle" in row_text or "apkm" in row_text or "split" in row_text
                        if prefer_split and not is_bundle:
                            continue

                        # Check architecture match
                        if arch in row_text or "universal" in row_text or "noarch" in row_text:
                            chosen_row = row
                            if is_bundle:
                                app_format = "BUNDLE"
                                app_ext = "apkm"
                            break

                    if not chosen_row and rows:
                        # Fallback to first row
                        chosen_row = rows[0]
                        if "bundle" in chosen_row.get_text().lower():
                            app_format = "BUNDLE"
                            app_ext = "apkm"

                    if chosen_row:
                        btn = chosen_row.select_one("a[href*='apk-download']") or chosen_row.select_one("a")
                        if btn:
                            target_variant_url = urllib.parse.urljoin(APKMIRROR_BASE, btn.get("href"))

            if not target_variant_url:
                target_variant_url = full_url

            # 2. Fetch variant download page
            r2 = requests.get(target_variant_url, headers=headers, timeout=10)
            if _is_challenge(r2):
                raise APKMirrorBlocked(target_variant_url)
            if r2.status_code != 200:
                return None

            soup2 = BeautifulSoup(r2.text, "html.parser")
            download_btn = soup2.select_one("a.accent_bg[href*='download/']") or soup2.select_one("a[href*='download.php']")
            if not download_btn:
                # Direct download page link
                download_btn = soup2.select_one("a[href*='download/?key=']")

            if not download_btn:
                return None

            step2_url = urllib.parse.urljoin(APKMIRROR_BASE, download_btn.get("href"))

            # 3. Final download page with direct link
            r3 = requests.get(step2_url, headers=headers, timeout=10)
            if _is_challenge(r3):
                raise APKMirrorBlocked(step2_url)
            if r3.status_code != 200:
                return None

            soup3 = BeautifulSoup(r3.text, "html.parser")
            final_link_elem = (
                soup3.select_one("a[rel='nofollow'][href*='download.php']")
                or soup3.select_one("a.accent_bg[href*='download.php']")
                or soup3.select_one("p.notes a[href*='download.php']")
            )

            if not final_link_elem:
                return None

            final_url = urllib.parse.urljoin(APKMIRROR_BASE, final_link_elem.get("href"))

            # Head request to find size
            size = 0
            try:
                head_r = requests.head(final_url, headers=headers, allow_redirects=True, timeout=5)
                size = int(head_r.headers.get("content-length", 0))
            except Exception:
                pass

            return final_url, app_format, size, app_ext
        except APKMirrorBlocked:
            raise
        except Exception:
            return None

    def download_app(
        self,
        app_name: str,
        version: str,
        download_url: str,
        ext: str,
        expected_size: int = 0,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> Optional[Path]:
        """Download APK / APKM to apps/<APP_NAME>/<version>.<ext>.

        Returns path on success, None on failure/cancel. Check cancel_event
        to distinguish cancel from error if needed.
        """
        target_dir = self.apps_dir / app_name
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = target_dir / f"{version}.{ext}"

        # Write .data metadata
        self._write_app_data(target_dir, ext, expected_size)

        if target_file.exists() and (expected_size <= 0 or target_file.stat().st_size == expected_size):
            return target_file

        result = download_file_ex(
            download_url,
            target_file,
            expected_size,
            progress_callback,
            cancel_event=cancel_event,
        )
        if result == DownloadResult.OK and target_file.exists():
            self._write_app_data(target_dir, ext, target_file.stat().st_size)
            return target_file
        return None

    def _write_app_data(self, target_dir: Path, ext: str, size: int) -> None:
        data_lines = [
            f"APP_FORMAT='{'BUNDLE' if ext != 'apk' else 'APK'}'",
            f"APP_EXT='{ext}'",
            f"APP_SIZE='{size}'",
        ]
        (target_dir / ".data").write_text("\n".join(data_lines) + "\n", encoding="utf-8")

    def adopt_browser_download(self, app_name: str, version: str, src: Path, ext: str) -> Path:
        """Move a file the user downloaded in the browser into apps/<app_name>/.

        Moved (not copied) so a large APK isn't kept twice. OSError propagates.
        """
        target_dir = self.apps_dir / app_name
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{version}.{ext}"
        target.unlink(missing_ok=True)
        shutil.move(str(src), str(target))
        self._write_app_data(target_dir, ext, target.stat().st_size)
        return target

    # --- Browser handoff (Cloudflare-blocked apps) ---

    def _pick_variant_url(self, apks: List[Dict[str, Any]]) -> Optional[str]:
        """Pick the best variant page for this device from the app_exists API's
        `apks` list: arch match (or noarch), minapi <= device SDK, highest version code."""
        arch = env.get_arch()
        try:
            sdk = int(env.getprop("ro.build.version.sdk", "0") or 0)
        except (TypeError, ValueError):
            sdk = 0

        def as_int(value: Any) -> int:
            try:
                return int(value or 0)
            except (TypeError, ValueError):
                return 0

        best_code = -1
        best_link = None
        for a in apks:
            link = a.get("link") or ""
            if not link:
                continue
            arches = a.get("arches") or []
            if arches and arch not in arches:
                continue
            if sdk and as_int(a.get("minapi")) > sdk:
                continue
            code = as_int(a.get("version_code"))
            if code > best_code:
                best_code = code
                best_link = link
        return urllib.parse.urljoin(APKMIRROR_BASE, best_link) if best_link else None

    def fetch_browser_versions(
        self,
        pkg_name: str,
        supported_versions: Optional[List[str]] = None,
        build_codes: Optional[Dict[str, str]] = None,
    ) -> List[ScrapedVersion]:
        """Version list built from APKMirror's app_exists API, which Cloudflare
        doesn't challenge. Only the latest release is known for sure; other
        supported versions are guessed release-page URLs (the browser shows
        APKMirror's 404 if one doesn't exist). build_codes maps version -> the
        build (version code) to pick on that page; it becomes the entry's note."""
        supported = supported_versions or []
        build_codes = build_codes or {}

        def note_for(version: str) -> str:
            code = build_codes.get(version)
            return f"build {code}" if code else ""

        try:
            r = requests.post(
                APP_EXISTS_URL, headers=APP_EXISTS_HEADERS, json={"pnames": [pkg_name]}, timeout=15
            )
            if r.status_code != 200:
                return []
            entries = r.json().get("data", [])
        except Exception:
            return []

        entry = next((e for e in entries if e.get("pname") == pkg_name and e.get("exists")), None)
        if not entry:
            return []
        release = entry.get("release") or {}
        latest = (release.get("version") or "").strip()
        release_link = release.get("link") or ""
        if not latest or not release_link:
            return []

        result = [
            ScrapedVersion(
                latest,
                "[RECOMMENDED]" if latest in supported else "[STABLE]",
                self._pick_variant_url(entry.get("apks") or [])
                or urllib.parse.urljoin(APKMIRROR_BASE, release_link),
                note_for(latest),
            )
        ]
        dashed = latest.replace(".", "-")
        if dashed in release_link:
            for v in supported:
                if v and v != latest:
                    result.append(ScrapedVersion(
                        v,
                        "[RECOMMENDED]",
                        urllib.parse.urljoin(APKMIRROR_BASE, release_link.replace(dashed, v.replace(".", "-"))),
                        note_for(v),
                    ))
        return order_versions(result)


def browser_download_dirs(candidates=BROWSER_DOWNLOAD_DIRS) -> List[Path]:
    """Readable Downloads directories, deduped by resolved path
    (~/storage/downloads is a symlink to /storage/emulated/0/Download)."""
    dirs: List[Path] = []
    seen = set()
    for c in candidates:
        try:
            if not c.is_dir():
                continue
            real = c.resolve()
            next(iter(real.iterdir()), None)
        except OSError:
            continue
        if real not in seen:
            seen.add(real)
            dirs.append(real)
    return dirs


def snapshot_downloads(dirs: List[Path]) -> Dict[Path, Tuple[float, int]]:
    """Map each .apk/.apkm in dirs to (mtime, size). Partial browser downloads
    (.crdownload etc.) are excluded by the suffix filter."""
    snap: Dict[Path, Tuple[float, int]] = {}
    for d in dirs:
        try:
            for p in d.iterdir():
                try:
                    if p.suffix.lower() in _BROWSER_EXTS and p.is_file():
                        st = p.stat()
                        snap[p] = (st.st_mtime, st.st_size)
                except OSError:
                    continue
        except OSError:
            continue
    return snap


def wait_for_browser_download(
    pkg_name: str,
    cancel_event: threading.Event,
    dirs: List[Path],
    before: Dict[Path, Tuple[float, int]],
    timeout: float = 900.0,
    poll_interval: float = 2.0,
    status_callback: Optional[Callable[[str], None]] = None,
) -> Optional[ExtractedAppMeta]:
    """Wait for a new, size-stable .apk/.apkm for pkg_name to appear in dirs.
    Returns its metadata, or None on cancel/timeout."""
    antisplit_mgr.ensure_aapt2()
    start = time.monotonic()
    deadline = start + timeout
    last_sizes: Dict[Path, int] = {}
    rejected = set()
    note = ""
    while not cancel_event.is_set() and time.monotonic() < deadline:
        current = snapshot_downloads(dirs)
        for p, (mtime, size) in current.items():
            if p in rejected or before.get(p) == (mtime, size):
                continue
            if not (size > 0 and last_sizes.get(p) == size):
                last_sizes[p] = size
                continue
            meta = antisplit_mgr.extract_metadata(p)
            # "com.unknown.app" is extract_metadata's fallback without aapt2.
            if meta and meta.pkg_name in (pkg_name, "com.unknown.app"):
                return meta
            rejected.add(p)
            note = f"Ignored {p.name}: not {pkg_name}"
        if status_callback:
            m, s = divmod(int(time.monotonic() - start), 60)
            status_callback(f"Waiting for the browser download… {m}:{s:02d}" + (f"\n{note}" if note else ""))
        cancel_event.wait(poll_interval)
    return None


# Global APKMirror scraper instance
apkmirror_scraper = APKMirrorScraper()
