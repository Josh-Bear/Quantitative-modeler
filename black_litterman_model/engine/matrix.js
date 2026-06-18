// ══════════════════════════════════════════════════════════════
// matrix.js — pure linear algebra helpers (no dependencies)
// All matrices are arrays of arrays (row-major). Vectors are 1-D arrays.
// ══════════════════════════════════════════════════════════════

const Matrix = (() => {

  function zeros(rows, cols) {
    return Array.from({ length: rows }, () => new Array(cols).fill(0));
  }

  function identity(n) {
    const I = zeros(n, n);
    for (let i = 0; i < n; i++) I[i][i] = 1;
    return I;
  }

  function transpose(A) {
    const rows = A.length, cols = A[0].length;
    const T = zeros(cols, rows);
    for (let i = 0; i < rows; i++)
      for (let j = 0; j < cols; j++) T[j][i] = A[i][j];
    return T;
  }

  // matrix × matrix
  function multiply(A, B) {
    const aRows = A.length, aCols = A[0].length, bCols = B[0].length;
    if (aCols !== B.length) throw new Error(`multiply: dim mismatch ${aCols} vs ${B.length}`);
    const C = zeros(aRows, bCols);
    for (let i = 0; i < aRows; i++)
      for (let k = 0; k < aCols; k++) {
        const aik = A[i][k];
        if (aik === 0) continue;
        for (let j = 0; j < bCols; j++) C[i][j] += aik * B[k][j];
      }
    return C;
  }

  // matrix × vector → vector
  function matVec(A, v) {
    if (A[0].length !== v.length) throw new Error('matVec: dim mismatch');
    return A.map(row => row.reduce((s, a, j) => s + a * v[j], 0));
  }

  function scale(A, s) {
    return A.map(row => row.map(x => x * s));
  }

  function add(A, B) {
    return A.map((row, i) => row.map((x, j) => x + B[i][j]));
  }

  function diag(vec) {
    const D = zeros(vec.length, vec.length);
    vec.forEach((v, i) => { D[i][i] = v; });
    return D;
  }

  // Gauss-Jordan inverse with partial pivoting.
  function inverse(A) {
    const n = A.length;
    // augmented [A | I]
    const M = A.map((row, i) => [...row, ...identity(n)[i]]);

    for (let col = 0; col < n; col++) {
      // pivot: largest magnitude in column
      let pivot = col;
      for (let r = col + 1; r < n; r++)
        if (Math.abs(M[r][col]) > Math.abs(M[pivot][col])) pivot = r;

      if (Math.abs(M[pivot][col]) < 1e-12)
        throw new Error('inverse: matrix is singular');

      [M[col], M[pivot]] = [M[pivot], M[col]];

      const pv = M[col][col];
      for (let j = 0; j < 2 * n; j++) M[col][j] /= pv;

      for (let r = 0; r < n; r++) {
        if (r === col) continue;
        const factor = M[r][col];
        if (factor === 0) continue;
        for (let j = 0; j < 2 * n; j++) M[r][j] -= factor * M[col][j];
      }
    }
    return M.map(row => row.slice(n));
  }

  // Add epsilon to the diagonal so a near-singular Σ stays invertible.
  function regularize(A, epsilon = 1e-8) {
    const R = A.map(row => row.slice());
    for (let i = 0; i < R.length; i++) R[i][i] += epsilon;
    return R;
  }

  // vᵀ A v  (quadratic form) → scalar
  function quadForm(v, A) {
    return v.reduce((s, vi, i) =>
      s + vi * v.reduce((t, vj, j) => t + A[i][j] * vj, 0), 0);
  }

  function dot(a, b) {
    return a.reduce((s, x, i) => s + x * b[i], 0);
  }

  return {
    zeros, identity, transpose, multiply, matVec,
    scale, add, diag, inverse, regularize, quadForm, dot,
  };
})();

if (typeof window !== 'undefined') window.Matrix = Matrix;
