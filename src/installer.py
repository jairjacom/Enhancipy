"""
Enhancify App Installer & Mounting Engine
Handles zipalign, custom keystore signing with apksigner / BouncyCastle,
Root mount/umount scripts, Rish privilege installs with Dex Optimizer,
and Non-privilege export to $STORAGE/Patched/.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, NamedTuple, Optional, Tuple

from src.config import config
from src.environment import env
from src.utils import rish_environ, run_command, run_rish


_RISH_ERROR_RE = re.compile(r"(?im)^\s*(?:error|failure)\b|invalid compiler filter|package not found")


def _first_rish_error_line(text: str) -> Optional[str]:
    """Return the first line of rish output that looks like a real error."""
    for line in text.splitlines():
        if _RISH_ERROR_RE.search(line):
            return line.strip()
    return None


CONFLICT_VERSION_DOWNGRADE = "version_downgrade"


class InstallResult(NamedTuple):
    """Outcome of install_or_export / uninstall_and_reinstall.

    `conflict` is a machine-readable reason the caller can act on (currently
    only CONFLICT_VERSION_DOWNGRADE); `exported_name` is the staged APK's
    name so the UI can retry the rish script after resolving the conflict.
    """

    ok: bool
    message: str
    conflict: Optional[str] = None
    exported_name: Optional[str] = None


def rish_export_name(app_name: str, app_ver: str, source_name: str) -> str:
    """Staged APK base name (no .apk) shared by install_or_export and retries."""
    return f"{app_name}-{app_ver.replace(':', '')}-{source_name}"


class AppInstaller:
    """Handles APK realignment, signing, and installation across privilege modes."""

    def __init__(self, workspace_dir: Optional[Path] = None):
        self.workspace_dir = workspace_dir or Path(__file__).resolve().parent.parent
        self.utils_dir = self.workspace_dir / "utils"
        self.system_dir = self.workspace_dir / "system"
        self.storage_dir = (self.workspace_dir / "storage") if workspace_dir else env.storage_dir
        self.zipalign_bin = self.utils_dir / "zipalign"
        self.keystore_dir = self.workspace_dir / "keystore"

    # --- Zipalign ---

    def realign_apk(self, apk_path: Path, progress_callback: Optional[Callable[[str], None]] = None) -> bool:
        """Align APK on 4-byte boundaries with 16-page alignment using zipalign."""
        if not self.zipalign_bin.exists():
            return False

        if not os.access(self.zipalign_bin, os.X_OK):
            try:
                self.zipalign_bin.chmod(0o755)
            except Exception:
                pass

        if progress_callback:
            progress_callback("Realigning APK on 4-byte boundaries...")

        aligned_tmp = apk_path.parent / f"{apk_path.stem}_aligned.apk"
        cmd = [str(self.zipalign_bin), "-f", "-P", "16", "4", str(apk_path), str(aligned_tmp)]
        code, out, err = run_command(cmd, timeout=30)

        if code == 0 and aligned_tmp.exists():
            shutil.move(str(aligned_tmp), str(apk_path))
            return True
        aligned_tmp.unlink(missing_ok=True)
        return False

    # --- Custom Keystore Signing ---

    def sign_with_custom_keystore(
        self,
        apk_path: Path,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> Tuple[bool, str]:
        """Sign APK using custom keystore, apksigner.jar, and Bouncy Castle."""
        keystore_json = self.keystore_dir / "keystore.json"
        if not self.keystore_dir.exists() or not keystore_json.exists():
            return False, "Custom keystore configuration not found!"

        # Find keystore file
        ks_files = list(self.keystore_dir.glob("*.p12")) + list(self.keystore_dir.glob("*.jks")) + \
                   list(self.keystore_dir.glob("*.pfx")) + list(self.keystore_dir.glob("*.keystore")) + \
                   list(self.keystore_dir.glob("*.jceks")) + list(self.keystore_dir.glob("*.uber")) + \
                   list(self.keystore_dir.glob("*.bks"))

        if not ks_files:
            return False, "No keystore file found in keystore directory!"

        ks_file = ks_files[0]
        try:
            ks_meta = json.loads(keystore_json.read_text(encoding="utf-8"))
            ks_info = ks_meta.get(ks_file.name, {})
        except Exception:
            return False, "Failed to read keystore.json metadata!"

        alias = ks_info.get("alias", "")
        ks_pass = ks_info.get("keystore_password", "")
        key_pass = ks_info.get("private_key_password", ks_pass)
        ks_type = ks_info.get("keystore_type", "PKCS12")

        if not alias or not ks_pass:
            return False, "Keystore alias or password missing in keystore.json!"

        apksigner_jar = next(self.utils_dir.glob("apksigner*.jar"), None)
        bc_jar = next(self.utils_dir.glob("bcprov*.jar"), None)

        if not apksigner_jar or not apksigner_jar.exists():
            return False, "apksigner.jar not found in utils directory!"

        if progress_callback:
            progress_callback(f"Signing APK with {ks_type} keystore ({ks_file.name})...")

        # Create temporary password files for apksigner
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f_kspass, \
             tempfile.NamedTemporaryFile(mode="w", delete=False) as f_keypass:
            f_kspass.write(ks_pass)
            f_keypass.write(key_pass)
            p_kspass = Path(f_kspass.name)
            p_keypass = Path(f_keypass.name)

        try:
            signed_out = apk_path.parent / f"{apk_path.stem}_signed.apk"

            if ks_type in ("UBER", "BKS"):
                if not bc_jar or not bc_jar.exists():
                    return False, f"Bouncy Castle provider JAR required for {ks_type} keystores!"

                cmd = [
                    "java",
                    "--enable-native-access=ALL-UNNAMED",
                    "-Xms100m",
                    "-Xmx512m",
                    "-cp",
                    f"{apksigner_jar}:{bc_jar}",
                    "com.android.apksigner.ApkSignerTool",
                    "sign",
                    "--provider-class",
                    "org.bouncycastle.jce.provider.BouncyCastleProvider",
                    "--provider-pos",
                    "1",
                    "--ks",
                    str(ks_file),
                    "--ks-pass",
                    f"file:{p_kspass}",
                    "--key-pass",
                    f"file:{p_keypass}",
                    "--ks-type",
                    ks_type,
                    "--ks-key-alias",
                    alias,
                    "--v1-signing-enabled",
                    "true",
                    "--v2-signing-enabled",
                    "true",
                    "--v3-signing-enabled",
                    "true",
                    "--v4-signing-enabled",
                    "false",
                    "--out",
                    str(signed_out),
                    str(apk_path),
                ]
            else:
                cmd = [
                    "java",
                    "--enable-native-access=ALL-UNNAMED",
                    "-Xms100m",
                    "-Xmx512m",
                    "-jar",
                    str(apksigner_jar),
                    "sign",
                    "--ks",
                    str(ks_file),
                    "--ks-pass",
                    f"file:{p_kspass}",
                    "--key-pass",
                    f"file:{p_keypass}",
                    "--ks-type",
                    ks_type,
                    "--ks-key-alias",
                    alias,
                    "--v1-signing-enabled",
                    "true",
                    "--v2-signing-enabled",
                    "true",
                    "--v3-signing-enabled",
                    "true",
                    "--v4-signing-enabled",
                    "false",
                    "--out",
                    str(signed_out),
                    str(apk_path),
                ]

            code, out, err = run_command(cmd, timeout=30)
            if code == 0 and signed_out.exists():
                shutil.move(str(signed_out), str(apk_path))
                return True, "APK signed successfully with custom keystore!"
            else:
                return False, f"Signing failed: {out}\n{err}"
        finally:
            p_kspass.unlink(missing_ok=True)
            p_keypass.unlink(missing_ok=True)

    # --- Mode-Specific Installation ---

    def run_dex_optimization(self, pkg_name: str, install_type: str = "new") -> Tuple[bool, str]:
        """Run dex optimization via Rish and verify it actually applied.

        rish always exits 0 regardless of the inner command's outcome
        (verified: `rish -c "exit 7"` -> 0), so success/failure is read from
        the rish output text, and the applied compiler filter is confirmed
        via dumpsys instead of trusted from the compile call alone.
        """
        # "quicken" was removed from the compiler-filter set on some ART
        # versions; try it first (cheap) on a fresh install and fall back to
        # "speed" (full AOT) if it's rejected or doesn't apply. Updates go
        # straight to a forced "speed" recompile.
        candidates = ["speed"] if install_type == "update" else ["quicken", "speed"]

        last_reason = "compile filter never applied"
        for index, mode in enumerate(candidates):
            force = "-f" if (install_type == "update" or index > 0) else ""
            compile_cmd = f"cmd package compile -m {mode} {force} {pkg_name}".replace("  ", " ").strip()
            # AOT ("speed") compilation of a large APK can take well over a
            # minute via rish/dex2oat, so compile calls get a generous budget.
            code, out, err = run_rish(compile_cmd, timeout=900)
            combined = out + err

            if code == 124:
                last_reason = "rish timed out"
                continue

            error_line = _first_rish_error_line(combined)
            if code != 0 or error_line:
                last_reason = error_line or f"rish exited {code}"
                if "package not found" in combined.lower():
                    return False, last_reason
                continue

            # dumpsys is a quick status query and keeps a short timeout.
            _, status_out, status_err = run_rish(f"dumpsys package {pkg_name}", timeout=60)
            pairs = re.findall(r"\[status=([^\]]+)\]\s*\[reason=([^\]]+)\]", status_out + status_err)

            if not pairs:
                # An unfamiliar dumpsys format (different Android release) is
                # not a dexopt failure - the compile attempt itself produced
                # no error text.
                return True, f"DEX optimized ({mode}, status unverified)"

            applied = any(
                (reason == "cmdline" and status == mode)
                or status in ("speed", "speed-profile", "everything")
                for status, reason in pairs
            )
            if applied:
                return True, f"DEX optimized ({mode})"

            last_reason = f"filter '{mode}' did not apply (dumpsys: {pairs[-1]})"

        return False, last_reason

    def install_or_export(
        self,
        apk_path: Path,
        app_name: str,
        pkg_name: str,
        app_ver: str,
        source_name: str,
        has_root: bool,
        has_rish: bool,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> InstallResult:
        """Finalize APK, realign, sign, and install/export according to privilege level."""
        # 1. Realign APK if custom keystore is used
        if config.is_on("Use_CUSTOM_KEYSTORE"):
            self.realign_apk(apk_path, progress_callback)
            ok, msg = self.sign_with_custom_keystore(apk_path, progress_callback)
            if not ok:
                return InstallResult(False, f"Signing failed: {msg}")

        # 2. Root Mode Mount
        if has_root:
            if progress_callback:
                progress_callback("Mounting patched APK via Root...")

            mount_script = self.system_dir / "mount.sh"
            if mount_script.exists():
                cmd = ["su", "-mm", "-c", f"/system/bin/sh {mount_script} {pkg_name} {app_name} {app_ver} {source_name}"]
                code, out, err = run_command(cmd, timeout=30)
                if code == 0:
                    if config.is_on("LAUNCH_APP_AFTER_MOUNT"):
                        launch_cmd = f"settings list secure | sed -n -e 's/\\/.*//' -e 's/default_input_method=//p' | xargs pidof | xargs kill -9 && pm resolve-activity --brief {pkg_name} | tail -n 1 | xargs am start -n"
                        subprocess.run(["su", "-c", launch_cmd], capture_output=True)
                    return InstallResult(True, f"{app_name} mounted successfully via Root!")
                return InstallResult(False, f"Root mounting failed: {err or out}")
            return InstallResult(False, "mount.sh script not found!")

        # 3. Rish Mode Installation
        elif has_rish:
            if progress_callback:
                progress_callback("Installing patched APK via Rish...")

            exported_name = rish_export_name(app_name, app_ver, source_name)
            target_storage_apk = self.storage_dir / "Patched" / f"{exported_name}.apk"
            target_storage_apk.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(apk_path, target_storage_apk)

            rish_script = self.system_dir / "rish-install.sh"
            if not rish_script.exists():
                return InstallResult(False, "rish-install.sh script not found!")

            self._clear_rish_result_files()
            code, out, err = self._run_rish_script(pkg_name, app_name, exported_name)
            if code == 0:
                return self._finish_rish_install(app_name, pkg_name, progress_callback)
            return self._rish_failure_result(exported_name, out, err)

        # 4. Non-Privilege Mode (Copy to Internal Storage)
        else:
            if progress_callback:
                progress_callback("Exporting patched APK to Internal Storage...")

            canonical_ver = app_ver.replace(":", "")
            exported_name = f"{app_name}-{canonical_ver}-{source_name}.apk"
            target_storage_apk = self.storage_dir / "Patched" / exported_name
            target_storage_apk.parent.mkdir(parents=True, exist_ok=True)

            try:
                shutil.copy2(apk_path, target_storage_apk)
                # Try opening with termux-open
                if shutil.which("termux-open"):
                    subprocess.run(["termux-open", "--view", str(target_storage_apk)], capture_output=True)
                return InstallResult(True, f"Non-privilege Mode — patched APK exported to:\n{target_storage_apk}")
            except Exception as e:
                return InstallResult(False, f"Failed to export APK: {e}")

    def _clear_rish_result_files(self) -> None:
        """Unlink the three files rish-install.sh writes, so a stale result
        from a previous run is never mistaken for this run's outcome."""
        (self.storage_dir / "install_error.txt").unlink(missing_ok=True)
        (self.storage_dir / "install_type.txt").unlink(missing_ok=True)
        (self.storage_dir / "install_failure_code.txt").unlink(missing_ok=True)
        (self.storage_dir / "rish_log.txt").unlink(missing_ok=True)

    def _run_rish_script(self, pkg_name: str, app_name: str, exported_name: str) -> Tuple[int, str, str]:
        """Invoke rish-install.sh once. Shared by the first install attempt and
        the uninstall+reinstall retry so they can never diverge."""
        rish_script = self.system_dir / "rish-install.sh"
        cmd = ["bash", str(rish_script), pkg_name, app_name, exported_name, str(self.storage_dir)]
        # The script performs ~8 rish round trips, moves a large APK,
        # then runs pm install - a short timeout can clip a slow
        # install into a bogus 124.
        return run_command(
            cmd,
            timeout=600,
            env=rish_environ({"ENHANCIFY_CONFIG_FILE": str(config.config_file)}),
        )

    def _finish_rish_install(
        self,
        app_name: str,
        pkg_name: str,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> InstallResult:
        install_type_file = self.storage_dir / "install_type.txt"
        install_type = "new"
        if install_type_file.exists():
            install_type = install_type_file.read_text().strip() or "new"

        # Run DEX Optimization
        if progress_callback:
            progress_callback("Running DEX Optimization via Rish...")
        dex_ok, dex_msg = self.run_dex_optimization(pkg_name, install_type)

        if config.is_on("LAUNCH_APP_AFTER_MOUNT"):
            run_rish(
                f"pm resolve-activity --brief {pkg_name} | tail -n 1 | xargs am start -n",
                timeout=60,
            )

        if dex_ok:
            return InstallResult(True, f"{app_name} installed successfully via Rish with Dex Optimization!")
        return InstallResult(True, f"{app_name} installed via Rish, but DEX optimization failed: {dex_msg}")

    def _rish_failure_result(self, exported_name: str, out: str, err: str) -> InstallResult:
        install_error_file = self.storage_dir / "install_error.txt"
        install_failure_code_file = self.storage_dir / "install_failure_code.txt"

        reason = ""
        if install_error_file.exists():
            reason = install_error_file.read_text().strip()
        if not reason:
            reason = (out + err).strip()
        if not reason:
            reason = "rish produced no output (Shizuku not authorized?)"

        conflict = None
        if install_failure_code_file.exists():
            if install_failure_code_file.read_text().strip() == "INSTALL_FAILED_VERSION_DOWNGRADE":
                conflict = CONFLICT_VERSION_DOWNGRADE

        return InstallResult(
            False,
            f"Rish installation failed: {reason}",
            conflict=conflict,
            exported_name=exported_name,
        )

    def uninstall_and_reinstall(
        self,
        app_name: str,
        pkg_name: str,
        exported_name: str,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> InstallResult:
        """Uninstall the currently installed package via rish, then rerun the
        rish install script against the already-staged APK. Used to resolve a
        version-downgrade conflict the user opted into."""
        if progress_callback:
            progress_callback("Uninstalling the currently installed version...")

        _, out, err = run_rish(f"pm uninstall --user current {pkg_name}", timeout=300)
        combined = out + err
        if "Success" not in combined:
            # Older pm builds reject --user current on uninstall.
            _, out, err = run_rish(f"pm uninstall {pkg_name}", timeout=300)
            combined = out + err

        if "Success" not in combined:
            stripped_lines = [line for line in combined.strip().splitlines() if line.strip()]
            reason = _first_rish_error_line(combined) or (stripped_lines[0] if stripped_lines else "")
            if not reason:
                reason = "rish produced no output (Shizuku not authorized?)"
            return InstallResult(False, f"Uninstall failed: {reason}")

        if progress_callback:
            progress_callback("Reinstalling patched APK via Rish...")

        self._clear_rish_result_files()
        code, out, err = self._run_rish_script(pkg_name, app_name, exported_name)
        if code == 0:
            return self._finish_rish_install(app_name, pkg_name, progress_callback)
        return self._rish_failure_result(exported_name, out, err)



# Global installer instance
app_installer = AppInstaller()
