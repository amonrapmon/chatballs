import { expect, it } from "vitest";
import { summarizeVisitor } from "./visitorState";
import type { VisitorObservation, VisitorState } from "./emailTypes";
const tab = (values: Partial<VisitorObservation>) => ({ widget: "closed", page: "visible", connection: "connected", ...values }) as VisitorObservation;
const state = (...tabs: VisitorObservation[]) => ({ sessions: [{ tabs }] }) as VisitorState;

it("uses actual visible tabs without allowing old lost documents to hide an open widget", () => {
  expect(summarizeVisitor(state(tab({ connection: "lost" }), tab({ widget: "open" })))).toMatchObject({ kind: "open" });
  expect(summarizeVisitor(state(tab({}), tab({ page: "hidden" })))).toMatchObject({ kind: "closed" });
  expect(summarizeVisitor(state(tab({ page: "hidden" }), tab({ page: "hidden" })))).toMatchObject({ kind: "hidden" });
});
it("reads the page shown after a navigation instead of the document that left the screen", () => {
  const left = tab({ widget: "open", page: "pagehide" });
  expect(summarizeVisitor(state(left, tab({})))).toMatchObject({ kind: "closed" });
  expect(summarizeVisitor(state(left, tab({ page: "hidden" })))).toMatchObject({ kind: "hidden" });
  expect(summarizeVisitor(state(left, tab({ page: "frozen" })))).toMatchObject({ kind: "unknown" });
  expect(summarizeVisitor(state(left))).toMatchObject({ kind: "unknown" });
});
it("keeps lifecycle and incomplete observations uncertain", () => {
  for (const page of ["pagehide", "pageshow", "resumed", "frozen", "unknown"] as const) {
    expect(summarizeVisitor(state(tab({ page })))).toMatchObject({ kind: "unknown" });
  }
  expect(summarizeVisitor(state(tab({ connection: "lost" }), tab({ connection: "unknown" })))).toMatchObject({ kind: "unknown" });
  expect(summarizeVisitor(state(tab({ widget: "unknown" })))).toMatchObject({ kind: "unknown" });
  expect(summarizeVisitor(null)).toMatchObject({ kind: "unknown" });
});
