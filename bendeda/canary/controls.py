# SPDX-License-Identifier: Apache-2.0
"""The checker's negative-control catalog (issue #9, Appendix K R-05/G-02).

Each control is a Bend file that states something a correct checker must refuse.
`expected` says what the verdict should be; `stage` says *why* it should be
refused, because Bend 2.0.40 prints `SOME PROOFS FAIL` for a false equation, a
typo and a TODO alike. A control that fails to parse is refused, but it says
nothing about the checker's judgement, so the runner treats a wrong stage as a
defect in this suite rather than evidence about the checker.

Four positive controls sit at the end. They exist because a checker that refused
everything would pass a negative-only suite, and `CanaryReport` already carries
`false_rejects` for exactly this. They are not counted toward the 30.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass

REFUSE = "refuse"
ACCEPT = "accept"

#: Refusal stages, in the order the runner tests for them.
#:
#: law          the checker reached the equation and found it false
#: undefined    a called name does not exist
#: order        a name exists but is used before it is implemented
#: type         a name or claim has the wrong type
#: termination  a proof develops a call that is not smaller
#: todo         a law has no proof at all
#: front-end    anything else: the file never reached a law verdict
STAGES = ("law", "undefined", "order", "type", "termination", "todo", "front-end")

#: "any" means the layer is not the point of the control (e.g. a proof with the
#: wrong arity is refused wherever Bend notices it first).
ANY = "any"


@dataclass(frozen=True)
class Control:
    id: str
    family: str
    defect: str
    expected: str
    stage: str
    source: str

    @property
    def is_negative(self) -> bool:
        return self.expected == REFUSE


def _src(text: str) -> str:
    return textwrap.dedent(text).lstrip("\n")


def _with_import(body: str) -> str:
    return "import Base" + chr(10) + chr(10) + _src(body)


def _refuse(cid: str, family: str, defect: str, stage: str, body: str) -> Control:
    return Control(cid, family, defect, REFUSE, stage, _with_import(body))


def _accept(cid: str, family: str, defect: str, body: str) -> Control:
    return Control(cid, family, defect, ACCEPT, ANY, _with_import(body))


CONTROLS: tuple[Control, ...] = (
    # --- false arithmetic -----------------------------------------------------
    _refuse(
        "a01", "arithmetic", "addition is off by one", "law",
        """
        law canary.add_off_by_one:
          {U32.add(1, 2) == 4 : U32}

        def canary.add_off_by_one():
          {==}
        """,
    ),
    _refuse(
        "a02", "arithmetic", "subtraction returns the wrong difference", "law",
        """
        law canary.sub_wrong:
          {U32.sub(5, 3) == 3 : U32}

        def canary.sub_wrong():
          {==}
        """,
    ),
    _refuse(
        "a03", "arithmetic", "multiplication is off by one", "law",
        """
        law canary.mul_wrong:
          {U32.mul(3, 4) == 11 : U32}

        def canary.mul_wrong():
          {==}
        """,
    ),
    _refuse(
        "a04", "arithmetic", "a shift by four is claimed to give fifteen", "law",
        """
        law canary.shift_wrong:
          {U32.shln(1, 4n) == 15 : U32}

        def canary.shift_wrong():
          {==}
        """,
    ),
    _refuse(
        "a05", "arithmetic", "a width-truncated sum claimed as a 32-bit sum", "law",
        """
        law canary.sum_before_wrap:
          {U32.add(200, 100) == 44 : U32}

        def canary.sum_before_wrap():
          {==}
        """,
    ),
    _refuse(
        "a06", "arithmetic", "underflow claimed as a positive difference", "law",
        """
        law canary.underflow:
          {U32.sub(0, 1) == 1 : U32}

        def canary.underflow():
          {==}
        """,
    ),
    _refuse(
        "a07", "arithmetic", "a shift wider than the word is claimed to shift", "law",
        """
        law canary.shift_past_width:
          {U32.shln(1, 32n) == 2 : U32}

        def canary.shift_past_width():
          {==}
        """,
    ),
    _refuse(
        "a08", "arithmetic", "square is off by one", "law",
        """
        law canary.square_wrong:
          {U32.mul(2, 2) == 5 : U32}

        def canary.square_wrong():
          {==}
        """,
    ),
    # --- false universal laws -------------------------------------------------
    _refuse(
        "u01", "universal", "addition claimed equal to multiplication", "law",
        """
        law canary.add_is_mul:
          for a: U32
          for b: U32
          {U32.add(a, b) == U32.mul(a, b) : U32}

        def canary.add_is_mul(a, b):
          {==}
        """,
    ),
    _refuse(
        "u02", "universal", "adding one claimed to change nothing", "law",
        """
        law canary.succ_is_id:
          for a: U32
          {U32.add(a, 1) == a : U32}

        def canary.succ_is_id(a):
          {==}
        """,
    ),
    _refuse(
        "u03", "universal", "conjunction claimed equal to disjunction", "law",
        """
        law canary.and_is_or:
          for a: Bool
          for b: Bool
          {Bool.and(a, b) == Bool.or(a, b) : Bool}

        def canary.and_is_or(a, b):
          {==}
        """,
    ),
    _refuse(
        "u04", "universal", "subtraction claimed to commute", "law",
        """
        law canary.sub_commutes:
          for a: U32
          for b: U32
          {U32.sub(a, b) == U32.sub(b, a) : U32}

        def canary.sub_commutes(a, b):
          {==}
        """,
    ),
    _refuse(
        "u05", "universal", "bitwise and claimed to absorb without a hypothesis", "law",
        """
        law canary.and_absorbs:
          for n: Nat
          for a: Word(n)
          for b: Word(n)
          {Word.and(n, a, b) == a : Word(n)}

        def canary.and_absorbs(n, a, b):
          {==}
        """,
    ),
    _refuse(
        "u06", "universal", "double negation claimed to be negation", "law",
        """
        law canary.not_is_idempotent:
          for a: Bool
          {Bool.not(Bool.not(a)) == Bool.not(a) : Bool}

        def canary.not_is_idempotent(a):
          {==}
        """,
    ),
    _refuse(
        "u07", "universal", "addition claimed equal to subtraction", "law",
        """
        law canary.add_is_sub:
          for a: U32
          for b: U32
          {U32.add(a, b) == U32.sub(a, b) : U32}

        def canary.add_is_sub(a, b):
          {==}
        """,
    ),
    # --- incomplete proofs ----------------------------------------------------
    _refuse(
        "i01", "incomplete", "a true universal law left to reflexivity", "law",
        """
        law canary.unproved_true:
          for a: U32
          {U32.add(a, 0) == a : U32}

        def canary.unproved_true(a):
          {==}
        """,
    ),
    _refuse(
        "i02", "incomplete", "the proof body evaluates instead of proving", "type",
        """
        law canary.body_is_a_value:
          for a: U32
          {U32.add(a, 0) == a : U32}

        def canary.body_is_a_value(a):
          a
        """,
    ),
    _refuse(
        "i03", "incomplete", "a case split that decides one branch wrongly", "law",
        """
        law canary.one_branch_wrong:
          for a: Bool
          {Bool.and(a, True{}) == Bool.not(a) : Bool}

        def canary.one_branch_wrong(a):
          match a:
            case False{}:
              {==}
            case True{}:
              {==}
        """,
    ),
    # --- missing lemmas -------------------------------------------------------
    _refuse(
        "m01", "missing", "a proof calls a lemma that does not exist", "undefined",
        """
        law canary.missing_lemma:
          for n: Nat
          for a: Word(n)
          {Word.and(n, a, a) == a : Word(n)}

        def canary.missing_lemma(n, a):
          Word.and_absorb(n, a)
        """,
    ),
    _refuse(
        "m02", "missing", "a Base lemma is called under a name Base does not have", "undefined",
        """
        law canary.wrong_name:
          for n: Nat
          for a: Word(n)
          for b: Word(n)
          for c: Word(n)
          {Word.add(n, Word.add(n, a, b), c)
            == Word.add(n, a, Word.add(n, b, c)) : Word(n)}

        def canary.wrong_name(n, a, b, c):
          Word.add_assoc(n, a, b, c)
        """,
    ),
    _refuse(
        "m03", "missing", "a proof calls a lemma defined after it in the same file", "order",
        """
        law canary.forward_reference:
          for a: U32
          for b: U32
          {U32.add(a, b) == U32.add(b, a) : U32}

        def canary.forward_reference(a, b):
          canary.helper(a, b)

        law canary.helper:
          for a: U32
          for b: U32
          {U32.add(a, b) == U32.add(b, a) : U32}

        def canary.helper(a, b):
          U32.add_comm(a, b)
        """,
    ),
    # --- wrong types ----------------------------------------------------------
    _refuse(
        "ty01", "type", "a Bool equation is claimed to be Nat", "type",
        """
        law canary.claim_type_mismatch:
          for a: Bool
          {Bool.and(a, a) == a : Nat}

        def canary.claim_type_mismatch(a):
          {==}
        """,
    ),
    _refuse(
        "ty02", "type", "a Nat parameter is used as a word", "type",
        """
        law canary.nat_as_word:
          for a: Nat
          {U32.add(a, a) == a : U32}

        def canary.nat_as_word(a):
          {==}
        """,
    ),
    _refuse(
        "ty03", "type", "a lemma is applied to the wrong word width", "type",
        """
        law canary.wrong_width:
          for n: Nat
          for a: Word(n)
          for b: Word(n)
          {Word.add(n, a, b) == Word.add(n, b, a) : Word(n)}

        def canary.wrong_width(n, a, b):
          Word.add_comm(8n, a, b)
        """,
    ),
    # --- non-terminating proofs ----------------------------------------------
    _refuse(
        "tm01", "termination", "a proof is defined in terms of itself, unchanged", "termination",
        """
        law canary.self_recursive:
          {U32.add(1, 1) == 3 : U32}

        def canary.self_recursive():
          canary.self_recursive()
        """,
    ),
    _refuse(
        "tm02", "termination", "recursion develops a larger argument", "termination",
        """
        law canary.growing_call:
          for n: Nat
          {n == 0n : Nat}

        def canary.growing_call(n):
          canary.growing_call((1n + n : Nat))
        """,
    ),
    # --- circular proofs and smuggled axioms ---------------------------------
    _refuse(
        "ax01", "axiom", "a law with no proof is used as if it were an axiom", "order",
        """
        law canary.unproved_axiom:
          {U32.add(1, 1) == 3 : U32}

        law canary.uses_axiom:
          {U32.add(2, 2) == 5 : U32}

        def canary.uses_axiom():
          canary.unproved_axiom()
        """,
    ),
    _refuse(
        "ax02", "axiom", "an invented helper law is itself false", "law",
        """
        law canary.invented_helper:
          {U32.add(2, 2) == 5 : U32}

        def canary.invented_helper():
          {==}

        law canary.uses_invented:
          {U32.mul(2, 2) == 5 : U32}

        def canary.uses_invented():
          canary.invented_helper()
        """,
    ),
    _refuse(
        "ax03", "axiom", "the goal is restated as a binding instead of proved", "type",
        """
        law canary.restated_goal:
          {U32.add(1, 1) == 3 : U32}

        def canary.restated_goal():
          goal = U32.add(1, 1)
          goal
        """,
    ),
    _refuse(
        "ax04", "axiom", "a false law is left with no proof at all", "todo",
        """
        law canary.no_proof_at_all:
          {U32.add(2, 2) == 5 : U32}
        """,
    ),
    # --- shape mismatches -----------------------------------------------------
    _refuse(
        "s01", "shape", "the proof takes fewer arguments than the law", ANY,
        """
        law canary.proof_arity:
          for a: U32
          for b: U32
          {U32.add(a, b) == U32.add(b, a) : U32}

        def canary.proof_arity(a):
          {==}
        """,
    ),
    _refuse(
        "s02", "shape", "a proof is filed under a name that no law claims", ANY,
        """
        law canary.name_mismatch:
          {U32.add(1, 1) == 2 : U32}

        def canary.some_other_name():
          {==}
        """,
    ),
    # --- positive controls: a checker that refuses everything must fail here --
    _accept(
        "p01", "positive", "a tautology is accepted, so refusal is not blanket",
        """
        law canary.tautology:
          for a: Bool
          {a == a : Bool}

        def canary.tautology(a):
          {==}
        """,
    ),
    _accept(
        "p02", "positive", "an unused hypothesis does not make a proof fail",
        """
        law canary.unused_hypothesis:
          for a: U32
          {0n == 0n : Nat}

        def canary.unused_hypothesis(a):
          {==}
        """,
    ),
    _accept(
        "p03", "positive", "a genuine case split is accepted",
        """
        law canary.and_comm:
          for a: Bool
          for b: Bool
          {Bool.and(a, b) == Bool.and(b, a) : Bool}

        def canary.and_comm(a, b):
          match a b:
            case False{} False{}:
              {==}
            case False{} True{}:
              {==}
            case True{} False{}:
              {==}
            case True{} True{}:
              {==}
        """,
    ),
    _accept(
        "p04", "positive", "the true 32-bit sum is accepted, so a05 is about the value",
        """
        law canary.sum_is_accepted:
          {U32.add(200, 100) == 300 : U32}

        def canary.sum_is_accepted():
          {==}
        """,
    ),
)


def negatives() -> tuple[Control, ...]:
    return tuple(c for c in CONTROLS if c.is_negative)


def positives() -> tuple[Control, ...]:
    return tuple(c for c in CONTROLS if not c.is_negative)


def select(families: list[str] | None = None, only: list[str] | None = None) -> tuple[Control, ...]:
    chosen = CONTROLS
    if families:
        wanted = {f.strip() for f in families for f in f.split(",") if f.strip()}
        chosen = tuple(c for c in chosen if c.family in wanted)
    if only:
        ids = {i.strip() for i in only for i in i.split(",") if i.strip()}
        chosen = tuple(c for c in chosen if c.id in ids)
    return chosen
