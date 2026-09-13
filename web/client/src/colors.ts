import type { PresentationGroup, ProofTerm } from "./types";

const COLOR_COUNT = 8;

/** Return the stable CSS palette class assigned to one presentation-group index. */
export function componentColorClass(index: number): string {
  return `component-color-${index % COLOR_COUNT}`;
}

/** Map each proof term to its exact group and stable palette position. */
export function termColorClasses(
  terms: ProofTerm[],
  groups: PresentationGroup[],
): Map<string, string> {
  const colors = new Map<string, string>();
  groups.forEach((group, groupIndex) => {
    group.termIds.forEach((termId) => {
      colors.set(termId, componentColorClass(groupIndex));
    });
  });
  terms.forEach((term, termIndex) => {
    if (!colors.has(term.id)) {
      colors.set(term.id, componentColorClass(groups.length + termIndex));
    }
  });
  return colors;
}

