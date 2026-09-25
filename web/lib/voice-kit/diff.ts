/**
 * A minimal line-oriented diff for the voice-kit editor pane's "Diff vs current" / version
 * "Compare" affordances (cmw-ui-wireframes screen 11). Voice-pack files are short markdown docs,
 * so a plain LCS diff is fast enough and needs no dependency.
 */

export type DiffLineType = "unchanged" | "added" | "removed";

export interface DiffLine {
  type: DiffLineType;
  text: string;
}

/** Line-by-line diff of `before` -> `after` via a longest-common-subsequence backtrack. */
export function diffLines(before: string, after: string): DiffLine[] {
  const a = before.split("\n");
  const b = after.split("\n");
  const n = a.length;
  const m = b.length;

  // lcs[i][j] = length of the LCS of a[i:] and b[j:]. Every index below is within [0, n]/[0, m]
  // by construction, so the non-null assertions just satisfy `noUncheckedIndexedAccess`.
  const lcs: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0));
  const lcsAt = (i: number, j: number): number => lcs[i]![j]!;
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      lcs[i]![j] = a[i] === b[j] ? lcsAt(i + 1, j + 1) + 1 : Math.max(lcsAt(i + 1, j), lcsAt(i, j + 1));
    }
  }

  const result: DiffLine[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    const lineA = a[i]!;
    const lineB = b[j]!;
    if (lineA === lineB) {
      result.push({ type: "unchanged", text: lineA });
      i++;
      j++;
    } else if (lcsAt(i + 1, j) >= lcsAt(i, j + 1)) {
      result.push({ type: "removed", text: lineA });
      i++;
    } else {
      result.push({ type: "added", text: lineB });
      j++;
    }
  }
  while (i < n) {
    result.push({ type: "removed", text: a[i]! });
    i++;
  }
  while (j < m) {
    result.push({ type: "added", text: b[j]! });
    j++;
  }
  return result;
}

/** Whether two texts differ at all — cheap guard before running the full diff/commit flow. */
export function hasChanges(before: string, after: string): boolean {
  return before !== after;
}
