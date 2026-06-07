/** Mirror backend command_intent.can_auto_approve for UI auto-run gating. */

const FIX_MARKERS = [
  "systemctl enable",
  "systemctl disable",
  "systemctl restart",
  "systemctl start",
  "systemctl stop",
  "mount -o remount",
  "sed -i",
  "chmod ",
  "chown ",
  "chgrp ",
  "setfacl",
  "useradd",
  "groupadd",
  "apt-get clean",
  "journalctl --vacuum",
  "-exec chown",
  "-exec chmod",
];

function intentFromCommand(commandText: string): "diagnostic" | "fix" | "validate" {
  const t = (commandText || "").trim().toLowerCase();
  if (!t) return "diagnostic";
  if (t.includes("public-test") || (t.startsWith("curl ") && t.includes("health"))) {
    return "validate";
  }
  if (
    t.includes("chmod") ||
    t.includes("chown") ||
    t.includes("systemctl restart") ||
    t.includes("systemctl start") ||
    t.includes("systemctl enable") ||
    t.includes("sed -i")
  ) {
    return "fix";
  }
  return "diagnostic";
}

export function canAutoApprove(commandText: string, safetyStatus?: string): boolean {
  if (safetyStatus === "Blocked") return false;
  const text = (commandText || "").trim();
  if (!text) return false;
  const lower = text.toLowerCase();
  if (FIX_MARKERS.some((m) => lower.includes(m))) return false;
  return intentFromCommand(text) === "diagnostic";
}

export function commandIntentLabel(commandText: string): string {
  return intentFromCommand(commandText);
}
