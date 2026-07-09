// Typed wrappers around the BL engine globals (§8).
//
// engine/matrix.js, engine/stats.js and engine/blacklitterman.js are classic
// (non-module) scripts loaded via <script> tags in frontend/index.html — they
// each set a window global. Classic scripts in <head> run before any module
// executes, so the globals are guaranteed to exist here.
//
// This is the ONLY file where `any` is allowed (spec rule).

/* eslint-disable @typescript-eslint/no-explicit-any */

declare global {
  interface Window {
    Matrix: any
    Stats: any
    BL: any
  }
}

export const Matrix: any = window.Matrix
export const Stats: any = window.Stats
export const BL: any = window.BL
