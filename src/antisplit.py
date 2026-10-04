"""
Enhancify Anti-Split & Native Library Optimizer Module
Handles merging APKM, APKS, and XAPK bundle files into standalone APKs using APKEditor.jar
and optimizing native libraries using aapt2 and zip. Both operations destroy the APK's
original certificate, so both re-sign the result with an internal throwaway keystore
afterward (see _sign_for_patching) so cert-dependent patches don't crash.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from src.deps import DependencyBootstrap
from src.environment import env
from src.utils import run_command

# Internal keystore used only to re-stamp a certificate onto APKs whose
# original signature was destroyed by this module's own processing (bundle
# merge discards per-split v2/v3 signatures; native-lib stripping deletes
# META-INF/*.SF/.RSA/.DSA/.EC). Cert-dependent patches (the Spoof Signature
# patch family used by e.g. license/paywall-bypass patches) only need *some*
# parseable certificate present at patch time -- they neutralize the app's
# own signature check to always report whatever was embedded at patch time,
# so the key/cert content is irrelevant. Password is a fixed, non-secret
# constant: this keystore never signs anything the user installs or
# distributes, it only has to make `java -jar <cli> patch` (and whatever
# patch logic reads the input APK's certificate) not crash.
_ANTISPLIT_KS_ALIAS = "antisplit"
_ANTISPLIT_KS_PASS = "enhancipy-antisplit"


LANGUAGE_MAP = {
    "en": "English", "es": "Spanish", "fr": "French", "de": "German",
    "it": "Italian", "pt": "Portuguese", "ru": "Russian", "zh": "Chinese",
    "ja": "Japanese", "ko": "Korean", "ar": "Arabic", "hi": "Hindi",
    "in": "Indonesian", "ms": "Malay", "th": "Thai", "vi": "Vietnamese",
    "tr": "Turkish",
}

DPI_BUCKETS = {
    "ldpi": 120, "mdpi": 160, "hdpi": 240,
    "xhdpi": 320, "xxhdpi": 480, "xxxhdpi": 640,
}


@dataclass
class ExtractedAppMeta:
    pkg_name: str
    app_name: str
    version_name: str
    extension: str
    file_path: Path


class AntiSplitManager:
    """Manages anti-split operations and native library optimization."""

    def __init__(self, workspace_dir: Optional[Path] = None):
        self.workspace_dir = workspace_dir or Path(__file__).resolve().parent.parent
        self.storage_dir = (self.workspace_dir / "storage") if workspace_dir else env.storage_dir
        self.utils_dir = self.workspace_dir / "utils"
        self.merge_keystore = self.storage_dir / "antisplit.keystore"
        self._deps = DependencyBootstrap(self.workspace_dir)
        self.bin_dir = self._deps.bin_dir
        self.aapt2_bin = self._deps.aapt2_bin
        self.apkeditor_jar = self._deps.apkeditor_jar

    def _ensure_signing_keystore(self) -> bool:
        """Generate the internal re-signing keystore (see module-level
        comment) via keytool if it doesn't exist yet."""
        if self.merge_keystore.exists():
            return True
        if not shutil.which("keytool"):
            return False
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        cmd = [
            "keytool", "-genkeypair", "-v",
            "-keystore", str(self.merge_keystore),
            "-storetype", "PKCS12",
            "-alias", _ANTISPLIT_KS_ALIAS,
            "-keyalg", "RSA", "-keysize", "2048", "-sigalg", "SHA512withRSA",
            "-validity", "10000",
            "-storepass", _ANTISPLIT_KS_PASS,
            "-keypass", _ANTISPLIT_KS_PASS,
            "-dname", "CN=EnhanciPy, OU=EnhanciPy, O=EnhanciPy, L=Unknown, ST=Unknown, C=US",
        ]
        code, _, _ = run_command(cmd, timeout=30)
        return code == 0 and self.merge_keystore.exists()

    def _sign_for_patching(self, apk_path: Path) -> bool:
        """Re-sign an APK that lost its original certificate during merge or
        native-lib stripping, so cert-dependent patches (e.g. Spoof
        Signature) can extract *a* certificate instead of crashing with
        NoCertificateException. Best-effort: on failure the caller still
        gets back the merged/stripped (certificate-less) APK, matching the
        pre-existing behavior."""
        if not apk_path.exists() or not self._ensure_signing_keystore():
            return False
        apksigner_jar = next(self.utils_dir.glob("apksigner*.jar"), None)
        if not apksigner_jar or not apksigner_jar.exists():
            return False

        signed_out = apk_path.parent / f"{apk_path.stem}_signed.apk"
        cmd = [
            "java", "--enable-native-access=ALL-UNNAMED",
            "-Xms100m", "-Xmx512m",
            "-jar", str(apksigner_jar), "sign",
            "--ks", str(self.merge_keystore),
            "--ks-pass", f"pass:{_ANTISPLIT_KS_PASS}",
            "--key-pass", f"pass:{_ANTISPLIT_KS_PASS}",
            "--ks-type", "PKCS12",
            "--min-sdk-version", "1",
            "--v1-signing-enabled", "true",
            "--v2-signing-enabled", "true",
            "--v3-signing-enabled", "true",
            "--v4-signing-enabled", "false",
            "--out", str(signed_out),
            str(apk_path),
        ]
        code, _, _ = run_command(cmd, timeout=60)
        if code == 0 and signed_out.exists():
            shutil.move(str(signed_out), str(apk_path))
            return True
        signed_out.unlink(missing_ok=True)
        return False

    def ensure_apkeditor(self) -> bool:
        """Download APKEditor.jar from the EnhanciPy deps release if missing."""
        return self._deps.ensure(only=["apkeditor"])[0]

    def ensure_aapt2(self) -> bool:
        """Download the arch-matched aapt2 binary if missing."""
        return self._deps.ensure(only=["aapt2"])[0]

    def get_closest_dpi_bucket(self) -> str:
        """Find the closest DPI bucket to the device density."""
        try:
            density = int(env.get_dpi())
        except Exception:
            density = 420

        closest = "nodpi"
        min_diff = 999999
        for name, val in DPI_BUCKETS.items():
            diff = abs(density - val)
            if diff < min_diff:
                min_diff = diff
                closest = name
        return closest

    # --- Metadata Extraction ---

    def extract_metadata(self, file_path: Path) -> Optional[ExtractedAppMeta]:
        """Extract package name, app label, and version from an APK or bundle."""
        file_path = Path(file_path)
        if not file_path.exists():
            return None

        ext = file_path.suffix.lstrip(".").lower()
        arch = env.get_arch()

        if ext == "apk":
            if self.aapt2_bin.exists():
                code, out, _ = run_command([str(self.aapt2_bin), "dump", "badging", str(file_path)])
                if code == 0:
                    pname_m = re.search(r"package:\s*name='([^']+)'", out)
                    label_m = re.search(r"application-label(?:-en)?:'([^']+)'", out)
                    ver_m = re.search(r"versionName='([^']+)'", out)

                    pkg_name = pname_m.group(1) if pname_m else ""
                    app_name = re.sub(r"[.:\s]+", "-", label_m.group(1)) if label_m else pkg_name
                    version = ver_m.group(1) if ver_m else "1.0"
                    if pkg_name:
                        return ExtractedAppMeta(pkg_name, app_name, version, "apk", file_path)

            # Fallback zip inspect
            try:
                with zipfile.ZipFile(file_path, "r") as zf:
                    if "AndroidManifest.xml" in zf.namelist():
                        return ExtractedAppMeta("com.unknown.app", file_path.stem, "1.0", "apk", file_path)
            except Exception:
                pass

        elif ext == "apkm":
            try:
                with zipfile.ZipFile(file_path, "r") as zf:
                    if "info.json" in zf.namelist():
                        info_data = json.loads(zf.read("info.json").decode("utf-8"))
                        pname = info_data.get("pname", "")
                        app_name = re.sub(r"[.:\s]+", "-", info_data.get("app_name", pname))
                        ver = info_data.get("release_version", "")
                        return ExtractedAppMeta(pname, app_name, ver, "apkm", file_path)
            except Exception:
                pass

        elif ext == "apks":
            try:
                with zipfile.ZipFile(file_path, "r") as zf:
                    if "base.apk" in zf.namelist():
                        with tempfile.NamedTemporaryFile(suffix=".apk", delete=False) as tmp:
                            tmp.write(zf.read("base.apk"))
                            tmp_path = Path(tmp.name)
                        meta = self.extract_metadata(tmp_path)
                        tmp_path.unlink(missing_ok=True)
                        if meta:
                            meta.extension = "apks"
                            meta.file_path = file_path
                            return meta
            except Exception:
                pass

        elif ext == "xapk":
            try:
                with zipfile.ZipFile(file_path, "r") as zf:
                    if "manifest.json" in zf.namelist():
                        man_data = json.loads(zf.read("manifest.json").decode("utf-8"))
                        pname = man_data.get("package_name", "")
                        app_name = re.sub(r"[.:\s]+", "-", man_data.get("name", pname))
                        ver = man_data.get("version_name", "")
                        return ExtractedAppMeta(pname, app_name, ver, "xapk", file_path)
            except Exception:
                pass

        return None

    # --- Antisplit Implementations ---

    def antisplit_apkm(self, input_apkm: Path, output_apk: Path) -> bool:
        """Unpack APKM bundle and merge using APKEditor.jar."""
        if not self.ensure_apkeditor() or not shutil.which("java"):
            return False

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            arch = env.get_arch().replace("-", "_")
            locale = env.get_locale()

            try:
                with zipfile.ZipFile(input_apkm, "r") as zf:
                    for name in zf.namelist():
                        if name == "base.apk" or f"split_config.{arch}.apk" in name or f"split_config.{locale}.apk" in name or "dpi.apk" in name:
                            zf.extract(name, tmp_path)
            except Exception:
                return False

            cmd = ["java", "-jar", str(self.apkeditor_jar), "m", "-f", "-i", str(tmp_path), "-o", str(output_apk), "-extractNativeLibs", "false"]
            code, _, _ = run_command(cmd, timeout=60)
            if code != 0 or not output_apk.exists():
                return False
            self._sign_for_patching(output_apk)
            return True

    def antisplit_apks(self, input_apks: Path, output_apk: Path) -> bool:
        """Unpack APKS bundle and merge using APKEditor.jar."""
        if not self.ensure_apkeditor() or not shutil.which("java"):
            return False

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            arch = env.get_arch().replace("-", "_")
            locale = env.get_locale()

            try:
                with zipfile.ZipFile(input_apks, "r") as zf:
                    for name in zf.namelist():
                        if name == "base.apk" or f"split_config.{arch}.apk" in name or f"split_config.{locale}.apk" in name or "dpi.apk" in name:
                            zf.extract(name, tmp_path)
            except Exception:
                return False

            cmd = ["java", "-jar", str(self.apkeditor_jar), "m", "-f", "-i", str(tmp_path), "-o", str(output_apk), "-extractNativeLibs", "false"]
            code, _, _ = run_command(cmd, timeout=60)
            if code != 0 or not output_apk.exists():
                return False
            self._sign_for_patching(output_apk)
            return True

    def antisplit_xapk(
        self,
        input_xapk: Path,
        output_apk: Path,
        selected_languages: Optional[List[str]] = None,
    ) -> bool:
        """Unpack XAPK bundle, copy splits for arch/dpi/languages, and merge."""
        if not self.ensure_apkeditor() or not shutil.which("java"):
            return False

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            try:
                with zipfile.ZipFile(input_xapk, "r") as zf:
                    zf.extractall(tmp_path)
            except Exception:
                return False

            manifest_file = tmp_path / "manifest.json"
            if not manifest_file.exists():
                return False

            try:
                manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
            except Exception:
                return False

            split_map: Dict[str, str] = {}
            for item in manifest.get("split_apks", []):
                split_map[item.get("id", "")] = item.get("file", "")

            base_file = split_map.get("base")
            if not base_file or not (tmp_path / base_file).exists():
                return False

            merge_dir = tmp_path / "merge"
            merge_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(tmp_path / base_file, merge_dir / "base.apk")

            # Arch split
            arch = env.get_arch().replace("-", "_")
            arch_split = f"config.{arch}"
            if arch_split in split_map and (tmp_path / split_map[arch_split]).exists():
                shutil.copy2(tmp_path / split_map[arch_split], merge_dir / split_map[arch_split])

            # DPI split
            dpi_bucket = self.get_closest_dpi_bucket()
            dpi_split = f"config.{dpi_bucket}"
            if dpi_split in split_map and (tmp_path / split_map[dpi_split]).exists():
                shutil.copy2(tmp_path / split_map[dpi_split], merge_dir / split_map[dpi_split])

            # Languages
            langs = selected_languages or ["config.en"]
            for lang_id in langs:
                if lang_id in split_map and (tmp_path / split_map[lang_id]).exists():
                    shutil.copy2(tmp_path / split_map[lang_id], merge_dir / split_map[lang_id])

            cmd = ["java", "-jar", str(self.apkeditor_jar), "m", "-f", "-i", str(merge_dir), "-o", str(output_apk), "-extractNativeLibs", "false"]
            code, _, _ = run_command(cmd, timeout=60)
            if code != 0 or not output_apk.exists():
                return False
            self._sign_for_patching(output_apk)
            return True

    # --- Native Library Optimization (RipLibs) ---

    def optimize_native_libs(self, apk_path: Path, progress_callback: Optional[Callable[[str], None]] = None) -> bool:
        """Strip unused native CPU architecture libraries from APK."""
        if not self.ensure_aapt2() or not apk_path.exists():
            return False

        arch = env.get_arch()
        if progress_callback:
            progress_callback(f"Analyzing native architectures for {arch}...")

        code, out, _ = run_command([str(self.aapt2_bin), "dump", "badging", str(apk_path)])
        if code != 0:
            return False

        native_code_match = re.search(r"native-code:\s*(.+)", out)
        if not native_code_match:
            return True  # No native libs, already optimal

        raw_libs = native_code_match.group(1).replace("'", "").split()
        if len(raw_libs) == 1 and raw_libs[0] == arch:
            return True  # Only device arch present

        if arch not in raw_libs:
            return False

        if progress_callback:
            progress_callback(f"Extracting and optimizing APK for {arch}...")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            with zipfile.ZipFile(apk_path, "r") as zf:
                zf.extractall(tmp_path)

            # Delete unused lib subdirectories
            lib_dir = tmp_path / "lib"
            if lib_dir.exists():
                for sub in lib_dir.iterdir():
                    if sub.is_dir() and sub.name != arch:
                        shutil.rmtree(sub, ignore_errors=True)

            # Strip signatures
            meta_inf = tmp_path / "META-INF"
            if meta_inf.exists():
                for sf in meta_inf.glob("*"):
                    if sf.suffix.upper() in [".SF", ".MF", ".RSA", ".DSA", ".EC"]:
                        sf.unlink(missing_ok=True)

            # Repackage APK. Native libs are stored uncompressed (matching
            # .arsc): valid regardless of the app's original
            # android:extractNativeLibs value (uncompressed+true is fine;
            # extractNativeLibs=false *requires* it -- a compressed lib with
            # extractNativeLibs=false is what causes `pm install` to fail
            # with "Failed to extract native libraries, res=-2"). Byte
            # alignment of these uncompressed entries is intentionally left
            # to the patch CLI's own "Aligning APK" pass, which always runs
            # downstream (this output is never installed without going
            # through run_patch first) -- any alignment applied here gets
            # reflowed anyway by _sign_for_patching's v1 JAR signing, and
            # re-aligning an already-v2/v3-signed APK with the vendored
            # zipalign corrupts the signing block (verified).
            rebuilt_apk = tmp_path / "temp.apk"
            with zipfile.ZipFile(rebuilt_apk, "w", zipfile.ZIP_DEFLATED) as zout:
                for root, _, files in os.walk(tmp_path):
                    for file in files:
                        if file == "temp.apk":
                            continue
                        fpath = Path(root) / file
                        arcname = fpath.relative_to(tmp_path)
                        arcname_str = str(arcname)
                        store_raw = arcname_str.endswith(".arsc") or arcname_str.startswith(f"lib{os.sep}") or arcname_str.startswith("lib/")
                        compress = zipfile.ZIP_STORED if store_raw else zipfile.ZIP_DEFLATED
                        zout.write(fpath, arcname, compress_type=compress)

            if rebuilt_apk.exists() and rebuilt_apk.stat().st_size > 0:
                shutil.move(str(rebuilt_apk), str(apk_path))
                self._sign_for_patching(apk_path)
                return True
            return False


# Global antisplit manager instance
antisplit_mgr = AntiSplitManager()
