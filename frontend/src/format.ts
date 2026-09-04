/** Decimal display rounds the string with BigInt, never via a binary float. */
export function number(value: string | number | null | undefined, digits = 4): string {
  if (value == null) return "—";
  if (!Number.isInteger(digits) || digits < 0 || digits > 12)
    throw new RangeError("Invalid display precision");
  const raw = String(value);
  const match = /^(-?)(\d+)(?:\.(\d*))?$/.exec(raw);
  if (!match) {
    if (typeof value === "number" && Number.isFinite(value))
      return value.toLocaleString("zh-CN", {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      });
    return "—";
  }
  const [, sign, whole, fraction = ""] = match;
  const factor = 10n ** BigInt(digits);
  let scaled =
    BigInt(whole) * factor + BigInt(fraction.slice(0, digits).padEnd(digits, "0") || "0");
  if (fraction.length > digits && Number(fraction[digits]) >= 5) scaled += 1n;
  return (
    (sign && scaled !== 0n ? "-" : "") +
    (scaled / factor).toLocaleString("zh-CN") +
    (digits ? "." + (scaled % factor).toString().padStart(digits, "0") : "")
  );
}
