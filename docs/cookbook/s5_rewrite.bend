# SPDX-License-Identifier: Apache-2.0
# Cookbook S5: rewriting with lemmas. `Equal.cong` replaces one side of an
# equality inside a context; `Equal.trans` chains two of those steps. Rewriting
# is directional: the lemma must be oriented so its left side appears in the
# goal, or the term will not typecheck.
import Base

law cook_s5_bool_and_idem:
  for a: Bool
  {Bool.and(a, a) == a : Bool}

def cook_s5_bool_and_idem(a):
  match a:
    case False{}:
      {==}
    case True{}:
      {==}

law cook_s5_word_and_idem:
  for n: Nat
  for a: Word(n)
  {Word.and(n, a, a) == a : Word(n)}

def cook_s5_word_and_idem(n, a):
  match n:
    case 0n:
      match a:
        case WNil{}:
          {==}
    case 1n+p:
      match a:
        case WCon{+h, +t}:
          bh = cook_s5_bool_and_idem(h)
          bt = cook_s5_word_and_idem(p, t)
          ab = Equal.cong(Bool, Word(1n+p), b => WCon{b, Word.and(p, t, t)},
            Bool.and(h, h), h, bh)
          bc = Equal.cong(Word(p), Word(1n+p), w => WCon{h, w},
            Word.and(p, t, t), t, bt)
          Equal.trans(Word(1n+p),
            WCon{Bool.and(h, h), Word.and(p, t, t)},
            WCon{h, Word.and(p, t, t)},
            WCon{h, t}, ab, bc)

law cook_s5_absorb:
  for n: Nat
  for a: Word(n)
  for b: Word(n)
  {Word.and(n, Word.and(n, a, a), b) == Word.and(n, a, b) : Word(n)}

def cook_s5_absorb(n, a, b):
  h = cook_s5_word_and_idem(n, a)
  Equal.cong(Word(n), Word(n), t => Word.and(n, t, b),
    Word.and(n, a, a), a, h)

law cook_s5_absorb_nested:
  for n: Nat
  for a: Word(n)
  for b: Word(n)
  for c: Word(n)
  {Word.and(n, c, Word.and(n, Word.and(n, a, a), b))
    == Word.and(n, c, Word.and(n, a, b)) : Word(n)}

def cook_s5_absorb_nested(n, a, b, c):
  h = cook_s5_absorb(n, a, b)
  Equal.cong(Word(n), Word(n), t => Word.and(n, c, t),
    Word.and(n, Word.and(n, a, a), b), Word.and(n, a, b), h)
