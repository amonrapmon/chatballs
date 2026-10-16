/** Intrinsic iframe sizing happens after history insertion. Keep the reader's
 * position when a card above the viewport grows, or follow it at the bottom. */
export function preserveSnapshotScroll(element: HTMLElement | null): () => void {
  let parent = element?.parentElement;
  while (parent && !/(auto|scroll)/.test(getComputedStyle(parent).overflowY)) parent = parent.parentElement;
  if (!parent || !element) return () => {};
  const node = parent;
  const height = node.scrollHeight;
  const top = node.scrollTop;
  const bottom = height - top - node.clientHeight < 32;
  const above = element.getBoundingClientRect().bottom < node.getBoundingClientRect().top;
  return () => {
    if (bottom) node.scrollTop = node.scrollHeight;
    else if (above) node.scrollTop = top + node.scrollHeight - height;
  };
}
