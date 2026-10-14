// Vendored shared layout metric contract.
// Mirrors production-runtime/adobe/editorial-layout.jsx `JFW.layoutMetrics` so the solver
// is self-contained on an experimental branch that must not modify the formal production
// runtime. When the formal file is present, pre-draw-layout.mjs prefers it; this copy is the
// fallback used on `main` (where editorial-layout.jsx does not yet exist).
// Keep the tokens in sync with the production contract if they change.
JFW.layoutMetrics={padX:4.5,padY:2.7,compactGap:3,framePad:3,arrowLength:3*72/25.4,minFontSize:6};
