# SPDX-License-Identifier: Apache-2.0
# Cookbook S6: lemma factoring. When the same sub-goal appears twice, state it
# once as an `aux_` lemma and rewrite with it in both places. The lemma must be
# general: an `aux_` lemma that only holds for the one value you needed is a
# proof of the example, not of the law.
import Base

law cook_s6_bool_and_idem:
  for a: Bool
  {Bool.and(a, a) == a : Bool}

def cook_s6_bool_and_idem(a):
  match a:
    case False{}:
      {==}
    case True{}:
      {==}

law aux_cook_s6_word_and_self:
  for n: Nat
  for a: Word(n)
  {Word.and(n, a, a) == a : Word(n)}

def aux_cook_s6_word_and_self(n, a):
  match n:
    case 0n:
      match a:
        case WNil{}:
          {==}
    case 1n+p:
      match a:
        case WCon{+h, +t}:
          bh = cook_s6_bool_and_idem(h)
          bt = aux_cook_s6_word_and_self(p, t)
          ab = Equal.cong(Bool, Word(1n+p), b => WCon{b, Word.and(p, t, t)},
            Bool.and(h, h), h, bh)
          bc = Equal.cong(Word(p), Word(1n+p), w => WCon{h, w},
            Word.and(p, t, t), t, bt)
          Equal.trans(Word(1n+p),
            WCon{Bool.and(h, h), Word.and(p, t, t)},
            WCon{h, Word.and(p, t, t)},
            WCon{h, t}, ab, bc)

law cook_s6_use_left:
  for n: Nat
  for a: Word(n)
  for b: Word(n)
  {Word.and(n, Word.and(n, a, a), b) == Word.and(n, a, b) : Word(n)}

def cook_s6_use_left(n, a, b):
  h = aux_cook_s6_word_and_self(n, a)
  Equal.cong(Word(n), Word(n), t => Word.and(n, t, b),
    Word.and(n, a, a), a, h)

law cook_s6_use_right:
  for n: Nat
  for a: Word(n)
  for b: Word(n)
  {Word.and(n, b, Word.and(n, a, a)) == Word.and(n, b, a) : Word(n)}

def cook_s6_use_right(n, a, b):
  h = aux_cook_s6_word_and_self(n, a)
  Equal.cong(Word(n), Word(n), t => Word.and(n, b, t),
    Word.and(n, a, a), a, h)
