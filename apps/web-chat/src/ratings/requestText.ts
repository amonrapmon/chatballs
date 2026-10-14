export function requestText(text: string) {
  const split = text.indexOf("?");
  return { heading: split >= 0 ? text.slice(0, split + 1) : text, body: split >= 0 ? text.slice(split + 1).trim() : "" };
}
