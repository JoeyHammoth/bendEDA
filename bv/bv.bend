# SPDX-License-Identifier: Apache-2.0
# BendBV: modular bit-vector arithmetic on U32 (Appendix K, G-01).
#
# Bend's only released type carrying and/shl/shr is U32, so a w-bit vector is a
# U32 with mask(w) applied on every operation. mask(w, x) = x & (2^w - 1),
# computed in U32: w = 0 gives 0, and w = 32 wraps the shift to 0, so the mask is
# 0xFFFFFFFF, the identity. Widths above 32 are out of scope for v1.
#
# Definitions, claims and proofs share one file. Bend 2.0.40 resolves imports
# against the working directory, not the importing file, and rejects a path
# containing `.bend` ("expected: an import path of plain names"), so a separate
# LAWS/PROOF pair would only check when the gate happened to run in the right
# directory. A single file checks the same from anywhere: `bend bv/bv.bend`.

import Base

# --- definitions ------------------------------------------------------------

def mask.unwrap(v: U32) -> Word(32n):
  match v:
    case U32{d}:
      d

def mask.bits(w: Nat) -> Word(32n):
  mask.unwrap(U32.sub(U32.shln(1, w), 1))

def mask(w: Nat, x: U32) -> U32:
  match x:
    case U32{xw}:
      U32{Word.and(32n, xw, mask.bits(w))}

def bv_add(w: Nat, a: U32, b: U32) -> U32:
  mask(w, U32.add(a, b))

def bv_sub(w: Nat, a: U32, b: U32) -> U32:
  mask(w, U32.sub(a, b))

# --- claims -----------------------------------------------------------------

law Bool.and_idem:
  for a: Bool
  {Bool.and(a, a) == a : Bool}

law Bool.and_comm:
  for a: Bool
  for b: Bool
  {Bool.and(a, b) == Bool.and(b, a) : Bool}

law Bool.and_assoc:
  for a: Bool
  for b: Bool
  for c: Bool
  {Bool.and(Bool.and(a, b), c) == Bool.and(a, Bool.and(b, c)) : Bool}

law Word.and_idem:
  for n: Nat
  for a: Word(n)
  {Word.and(n, a, a) == a : Word(n)}

law Word.and_assoc:
  for n: Nat
  for a: Word(n)
  for b: Word(n)
  for c: Word(n)
  {Word.and(n, Word.and(n, a, b), c) == Word.and(n, a, Word.and(n, b, c)) : Word(n)}

law mask.idem:
  for +w: Nat
  for x: U32
  {mask(w, mask(w, x)) == mask(w, x) : U32}

law bv_add.comm:
  for +w: Nat
  for a: U32
  for b: U32
  {bv_add(w, a, b) == bv_add(w, b, a) : U32}

law bv_add.wrap8:
  {bv_add(8n, 200, 100) == 44 : U32}

# --- proofs -----------------------------------------------------------------

def Bool.and_idem(a):
  match a:
    case False{}:
      {==}
    case True{}:
      {==}

def Bool.and_comm(a, b):
  match a b:
    case False{} False{}:
      {==}
    case False{} True{}:
      {==}
    case True{} False{}:
      {==}
    case True{} True{}:
      {==}

def Bool.and_assoc(a, b, c):
  match a b c:
    case False{} False{} False{}:
      {==}
    case False{} False{} True{}:
      {==}
    case False{} True{} False{}:
      {==}
    case False{} True{} True{}:
      {==}
    case True{} False{} False{}:
      {==}
    case True{} False{} True{}:
      {==}
    case True{} True{} False{}:
      {==}
    case True{} True{} True{}:
      {==}

def Word.and_idem(n, a):
  match n:
    case 0n:
      match a:
        case WNil{}:
          {==}
    case 1n+p:
      match a:
        case WCon{+h, +t}:
          bh = Bool.and_idem(h)
          bt = Word.and_idem(p, t)
          ab = Equal.cong(Bool, Word(1n+p), b => WCon{b, Word.and(p, t, t)},
            Bool.and(h, h), h, bh)
          bc = Equal.cong(Word(p), Word(1n+p), w => WCon{h, w},
            Word.and(p, t, t), t, bt)
          Equal.trans(Word(1n+p),
            WCon{Bool.and(h, h), Word.and(p, t, t)},
            WCon{h, Word.and(p, t, t)},
            WCon{h, t}, ab, bc)

def Word.and_assoc(n, a, b, c):
  match n:
    case 0n:
      match a b c:
        case WNil{} WNil{} WNil{}:
          {==}
    case 1n+p:
      match a b c:
        case WCon{+ah, +at} WCon{+bh, +bt} WCon{+ch, +ct}:
          hh = Bool.and_assoc(ah, bh, ch)
          tt = Word.and_assoc(p, at, bt, ct)
          e1 = Equal.cong(Bool, Word(1n+p),
            h => WCon{h, Word.and(p, Word.and(p, at, bt), ct)},
            Bool.and(Bool.and(ah, bh), ch), Bool.and(ah, Bool.and(bh, ch)), hh)
          e2 = Equal.cong(Word(p), Word(1n+p),
            t => WCon{Bool.and(ah, Bool.and(bh, ch)), t},
            Word.and(p, Word.and(p, at, bt), ct),
            Word.and(p, at, Word.and(p, bt, ct)), tt)
          Equal.trans(Word(1n+p),
            WCon{Bool.and(Bool.and(ah, bh), ch), Word.and(p, Word.and(p, at, bt), ct)},
            WCon{Bool.and(ah, Bool.and(bh, ch)), Word.and(p, Word.and(p, at, bt), ct)},
            WCon{Bool.and(ah, Bool.and(bh, ch)), Word.and(p, at, Word.and(p, bt, ct))},
            e1, e2)

def mask.idem(w, x):
  match x:
    case U32{+xw}:
      +ww = w
      h1 = Word.and_assoc(32n, xw, mask.bits(ww), mask.bits(ww))
      h2 = Equal.cong(Word(32n), Word(32n), t => Word.and(32n, xw, t),
        Word.and(32n, mask.bits(ww), mask.bits(ww)), mask.bits(ww),
        Word.and_idem(32n, mask.bits(ww)))
      h3 = Equal.trans(Word(32n),
        Word.and(32n, Word.and(32n, xw, mask.bits(ww)), mask.bits(ww)),
        Word.and(32n, xw, Word.and(32n, mask.bits(ww), mask.bits(ww))),
        Word.and(32n, xw, mask.bits(ww)), h1, h2)
      Equal.cong(Word(32n), U32, t => U32{t},
        Word.and(32n, Word.and(32n, xw, mask.bits(ww)), mask.bits(ww)),
        Word.and(32n, xw, mask.bits(ww)), h3)

def bv_add.comm(w, a, b):
  match a b:
    case U32{+aw} U32{+bw}:
      +ww = w
      h2 = Equal.cong(Word(32n), Word(32n), t => Word.and(32n, t, mask.bits(ww)),
        Word.add(32n, aw, bw), Word.add(32n, bw, aw), Word.add_comm(32n, aw, bw))
      Equal.cong(Word(32n), U32, t => U32{t},
        Word.and(32n, Word.add(32n, aw, bw), mask.bits(ww)),
        Word.and(32n, Word.add(32n, bw, aw), mask.bits(ww)), h2)

def bv_add.wrap8():
  {==}
