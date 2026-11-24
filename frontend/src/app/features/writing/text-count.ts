/** Words as congresses usually count them: sequences separated by spaces or line breaks. */
export function countWords(text: string): number {
  const trimmed = text.trim();
  return trimmed ? trimmed.split(/\s+/u).length : 0;
}
