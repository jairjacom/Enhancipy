#!/usr/bin/bash

rish() {
    local _rish_del _rish_strip
    _rish_del='/^[[:space:]]*Entering shell\.\.*[[:space:]]*$/d'
    _rish_strip='s/^[[:space:]]*Entering shell\.\.*[[:space:]]*//'
    command rish "$@" 2>&1 | sed -e "$_rish_del" -e "$_rish_strip"
    return "${PIPESTATUS[0]}"
}

[ -z "$RISH_APPLICATION_ID" ] && export RISH_APPLICATION_ID="com.termux"
[ -z "$MANAGER_APPLICATION_ID" ] && export MANAGER_APPLICATION_ID="moe.shizuku.privileged.api"

PKG_NAME="$1"
APP_NAME="$2"
EXPORTED_APK_NAME="$3"
STORAGE="$4"
INSTALL_TYPE_OVERRIDE="$5"

if [ -z "$STORAGE" ]; then
    log() { echo "$1"; }
else
    log() { echo "- $1" >> "$STORAGE/rish_log.txt"; }
fi

log ""
log "      Initiating rish installation"
log "package: $PKG_NAME"
log "app name: $APP_NAME"
log "exported APK name: $EXPORTED_APK_NAME"
log ""

CURRENT_USER=$(rish -c "am get-current-user" | tr -cd '0-9')
CURRENT_USER=${CURRENT_USER:-0}
log "Current user: $CURRENT_USER"

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
CONFIG_FILE="${ENHANCIFY_CONFIG_FILE:-$SCRIPT_DIR/../.config}"
SKIP_VERIFICATION="off"
BYPASS_LOW_TARGET_SDK_BLOCK="off"
ALLOW_APP_VERSION_DOWNGRADE="off"

if [ -f "$CONFIG_FILE" ]; then
    log "Config file found at: $CONFIG_FILE"

    SKIP_VERIFICATION=$(grep "^SKIP_VERIFICATION=" "$CONFIG_FILE" | cut -d"'" -f2)
    BYPASS_LOW_TARGET_SDK_BLOCK=$(grep "^BYPASS_LOW_TARGET_SDK_BLOCK=" "$CONFIG_FILE" | cut -d"'" -f2)
    ALLOW_APP_VERSION_DOWNGRADE=$(grep "^ALLOW_APP_VERSION_DOWNGRADE=" "$CONFIG_FILE" | cut -d"'" -f2)

    SKIP_VERIFICATION=${SKIP_VERIFICATION:-off}
    BYPASS_LOW_TARGET_SDK_BLOCK=${BYPASS_LOW_TARGET_SDK_BLOCK:-off}
    ALLOW_APP_VERSION_DOWNGRADE=${ALLOW_APP_VERSION_DOWNGRADE:-off}

    log "Config: SKIP_VERIFICATION='$SKIP_VERIFICATION'"
    log "Config: BYPASS_LOW_TARGET_SDK_BLOCK='$BYPASS_LOW_TARGET_SDK_BLOCK'"
    log "Config: ALLOW_APP_VERSION_DOWNGRADE='$ALLOW_APP_VERSION_DOWNGRADE'"
else
    log "Config file not found at: $CONFIG_FILE (using defaults)"
    log "Config: SKIP_VERIFICATION='$SKIP_VERIFICATION'"
    log "Config: BYPASS_LOW_TARGET_SDK_BLOCK='$BYPASS_LOW_TARGET_SDK_BLOCK'"
    log "Config: ALLOW_APP_VERSION_DOWNGRADE='$ALLOW_APP_VERSION_DOWNGRADE'"
fi

PATCHED_APP_PATH="/data/local/tmp/enhancify/$PKG_NAME.apk"
EXPORTED_APP_PATH="/storage/emulated/$CURRENT_USER/Enhancify/Patched/$EXPORTED_APK_NAME.apk"

if [ -n "$INSTALL_TYPE_OVERRIDE" ]; then
    INSTALL_TYPE="$INSTALL_TYPE_OVERRIDE"
    log "Install type override provided: $INSTALL_TYPE"
else
    INSTALL_TYPE="new"
    if echo "$(rish -c "pm list packages --user current | grep -q $PKG_NAME && echo Installed")" | grep -qx "Installed"; then
        INSTALL_TYPE="update"
        CURRENT_VERSION=$(rish -c "dumpsys package $PKG_NAME" | sed -n '/versionName/s/.*=//p' | sed -n '1p' | tr -d '\r')
        log "Existing installation detected (v$CURRENT_VERSION) - this will be an UPDATE"
    else
        log "No existing installation detected - this will be a NEW INSTALL"
    fi
fi

if [ -n "$STORAGE" ]; then
    echo "$INSTALL_TYPE" > "$STORAGE/install_type.txt"
    log "Install type written to $STORAGE/install_type.txt: $INSTALL_TYPE"
fi

if echo "$(rish -c "[ -d '/data/local/tmp/enhancify' ] && echo Exists || echo Missing")" | grep -qx "Exists"; then
    rish -c "mkdir '/data/local/tmp/enhancify'"
    log "/data/local/tmp/enhancify created."
fi

if echo "$(rish -c "[ -e $PATCHED_APP_PATH ] && echo Exists || echo Missing")" | grep -qx "Exists"; then
    rish -c "rm $PATCHED_APP_PATH"
    log "Residual $PATCHED_APP_PATH deleted"
fi

log "Moving exported APK to /data/local/tmp/enhancify..."
rish -c "mv -f $EXPORTED_APP_PATH $PATCHED_APP_PATH"

if echo "$(rish -c "[ -e $PATCHED_APP_PATH ] && echo Exists || echo Missing")" | grep -qx "Missing"; then
    log "Failed to move patched APK to $PATCHED_APP_PATH"
    [ -n "$STORAGE" ] && echo "Failed to stage APK for installation (move to /data/local/tmp failed)" > "$STORAGE/install_error.txt"
    exit 1
fi

DEVICE_SDK=$(rish -c "getprop ro.build.version.sdk" | tr -cd '0-9')
DEVICE_SDK=${DEVICE_SDK:-0}
log "Device SDK: $DEVICE_SDK"

INSTALL_FLAGS=""

if [ "$SKIP_VERIFICATION" == "on" ]; then
    if [ "$DEVICE_SDK" -ge 34 ]; then
        INSTALL_FLAGS="$INSTALL_FLAGS --skip-verification"
        log "Adding flag: --skip-verification"
    else
        log "Skipping --skip-verification (needs SDK 34+, device is $DEVICE_SDK)"
    fi
fi

if [ "$BYPASS_LOW_TARGET_SDK_BLOCK" == "on" ]; then
    if [ "$DEVICE_SDK" -ge 34 ]; then
        INSTALL_FLAGS="$INSTALL_FLAGS --bypass-low-target-sdk-block"
        log "Adding flag: --bypass-low-target-sdk-block"
    else
        log "Skipping --bypass-low-target-sdk-block (needs SDK 34+, device is $DEVICE_SDK)"
    fi
fi

if [ "$ALLOW_APP_VERSION_DOWNGRADE" == "on" ]; then
    INSTALL_FLAGS="$INSTALL_FLAGS -d"
    log "Adding flag: -d (allow version downgrade)"
fi

CMD_RISH="pm install -r -i com.android.vending$INSTALL_FLAGS --user current $PATCHED_APP_PATH"
OUTPUT=$(rish -c "$CMD_RISH")
log "Install command: $CMD_RISH"
log "Install output: $OUTPUT"

if [ -n "$INSTALL_FLAGS" ] && echo "$OUTPUT" | grep -qi -e "Unknown option" -e "Unrecognized option" -e "Bad argument"; then
    log "pm rejected install flags on this Android version - retrying without them"
    CMD_RISH="pm install -r -i com.android.vending --user current $PATCHED_APP_PATH"
    OUTPUT=$(rish -c "$CMD_RISH")
    log "Retry install command: $CMD_RISH"
    log "Retry install output: $OUTPUT"
fi

parse_install_failure() {
    local output="$1"
    local reason=""

    if echo "$output" | grep -qoP 'Failure \[.*?\]'; then
        reason=$(echo "$output" | grep -oP 'Failure \[\K[^\]]+' | head -1)
    elif echo "$output" | grep -qi "exception"; then
        reason=$(echo "$output" | grep -i "exception" | head -1 | sed 's/^[[:space:]]*//')
    elif echo "$output" | grep -qi "security"; then
        reason=$(echo "$output" | grep -i "security" | head -1 | sed 's/^[[:space:]]*//')
    elif echo "$output" | grep -qi "^error\|error:"; then
        reason=$(echo "$output" | grep -i "error" | head -1 | sed 's/^[[:space:]]*//')
    else
        reason=$(echo "$output" | head -3 | tr '\n' ' ' | sed 's/[[:space:]]*$//')
        reason="Unknown error: $reason"
    fi

    echo "$reason"
}

if echo "$OUTPUT" | grep -q "^Success"; then
    log "Install succeeded."
    rish -c "rm -f $PATCHED_APP_PATH"
    [ -n "$STORAGE" ] && rm -f "$STORAGE/install_error.txt"
    [ -n "$STORAGE" ] && rm -f "$STORAGE/install_failure_code.txt"
    exit 0
else
    FAILURE_REASON=$(parse_install_failure "$OUTPUT")
    log "Install failed."
    log "Failure reason: $FAILURE_REASON"

    [ -n "$STORAGE" ] && echo "$FAILURE_REASON" > "$STORAGE/install_error.txt"

    FAILURE_CODE=$(echo "$OUTPUT" | grep -o 'INSTALL_FAILED_[A-Z_]*' | head -1)
    FAILURE_CODE=${FAILURE_CODE:-UNKNOWN}
    log "Failure code: $FAILURE_CODE"
    [ -n "$STORAGE" ] && echo "$FAILURE_CODE" > "$STORAGE/install_failure_code.txt"

    log "Moving APK back to original location."
    rish -c "mv -f $PATCHED_APP_PATH $EXPORTED_APP_PATH"
    exit 1
fi
