import { KEEP_ENGLISH_TERMS } from "./terminology";

const TECHNICAL_TOKEN = /^[A-Z0-9_./:-]+$/;
const PROTECTED_TERMS = [...KEEP_ENGLISH_TERMS].sort((left, right) => right.length - left.length);

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** QA-only text expansion enabled with ?pseudo=1. */
export function pseudoLocalize(value: string): string {
  const protectedValues: string[] = [];
  let protectedText = value;
  for (const term of PROTECTED_TERMS) {
    const pattern = new RegExp(`(?<![A-Za-z])${escapeRegExp(term)}(?![A-Za-z])`, "g");
    protectedText = protectedText.replace(pattern, (match) => {
      const marker = `\u0000${protectedValues.length}\u0000`;
      protectedValues.push(match);
      return marker;
    });
  }
  const expanded = protectedText.replace(/[^\s]+/g, (token) => {
    if (TECHNICAL_TOKEN.test(token)) return token;
    const expanded = token.replace(/[A-Za-z]{3,}/g, (word) => `${word}·${word.slice(0, Math.max(1, Math.ceil(word.length * 0.35)))}`);
    return `[${expanded}]`;
  });
  return expanded.replace(/\u0000(\d+)\u0000/g, (_, index: string) => protectedValues[Number(index)] || "");
}
