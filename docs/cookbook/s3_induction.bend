# SPDX-License-Identifier: Apache-2.0
# Cookbook S3: induction. `match n` on a Nat gives the base case 0n and the step
# case 1n+p, and the recursive call on p is the induction hypothesis. The step
# case of a word law rebuilds the constructor, so the goal is an equality of two
# `WCon` values; `Equal.cong` lifts the head and tail hypotheses into it and
# `Equal.trans` chains them.
import Base

law cook_s3_bool_and_idem:
  for a: Bool
  {Bool.and(a, a) == a : Bool}

def cook_s3_bool_and_idem(a):
  match a:
    case False{}:
      {==}
    case True{}:
      {==}

law cook_s3_word_and_idem:
  for n: Nat
  for a: Word(n)
  {Word.and(n, a, a) == a : Word(n)}

def cook_s3_word_and_idem(n, a):
  match n:
    case 0n:
      match a:
        case WNil{}:
          {==}
    case 1n+p:
      match a:
        case WCon{+h, +t}:
          bh = cook_s3_bool_and_idem(h)
          bt = cook_s3_word_and_idem(p, t)
          # The hypothesis is used twice, so the word `t` is bound with `+`:
          # Bend bindings are affine and `Word.and(p, t, t)` reads `t` twice.
          ab = Equal.cong(Bool, Word(1n+p), b => WCon{b, Word.and(p, t, t)},
            Bool.and(h, h), h, bh)
          bc = Equal.cong(Word(p), Word(1n+p), w => WCon{h, w},
            Word.and(p, t, t), t, bt)
          Equal.trans(Word(1n+p),
            WCon{Bool.and(h, h), Word.and(p, t, t)},
            WCon{h, Word.and(p, t, t)},
            WCon{h, t}, ab, bc)
