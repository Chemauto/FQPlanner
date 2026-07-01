"""ShadowState — agent-side belief tracker, no oracle access.

Rule:
  location / open  → updated from command + observation text
  clean / hot / cold / sliced → provenance only; never inferred from observation

Key insight: "the cup looks clean" ≠ "I cleaned the cup."
This is the gap that breaks naive perception-based judges in real deployment.
"""
from __future__ import annotations

import re


def _base(s: str) -> str:
    """'countertop 1' → 'countertop'  |  'mug 1' → 'mug'"""
    return re.sub(r"\s*\d+$", "", str(s).strip().lower())


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).strip().lower())


class ShadowState:
    """Tracks agent belief state from (command, observation) pairs.

    Objects stored by full instance name ('mug 1'); judge() matches by type base.
    Provenance sets (cleaned/heated/cooled/sliced) also use full instance names.
    """

    def __init__(self) -> None:
        self.at: dict[str, str] = {}        # "mug 1" → "countertop" | "held"
        self.holding: str | None = None     # full name or None
        self.is_open: set[str] = set()      # full receptacle names that are open
        # Provenance — never updated from observation:
        self.cleaned: set[str] = set()
        self.heated: set[str] = set()
        self.cooled: set[str] = set()
        self.sliced: set[str] = set()

    # ── update ────────────────────────────────────────────────────────────────

    def update(self, command: str, observation: str) -> None:
        """Process one (command, observation) pair after execution."""
        cmd = _norm(command)
        obs = _norm(observation)
        if obs.startswith("nothing happens"):
            return

        if cmd.startswith("take "):
            m = re.match(r"take (.+?) from ", cmd)
            if m:
                obj = m.group(1).strip()
                self.at[obj] = "held"
                self.holding = obj

        elif cmd.startswith("move ") or cmd.startswith("put "):
            m = re.match(r"(?:move|put) (.+?) (?:in(?:to)?|on(?:to)?|to) (.+)", cmd)
            if m:
                obj = m.group(1).strip()
                dst = _base(m.group(2).strip())
                self.at[obj] = dst
                self.holding = None

        elif cmd.startswith("open "):
            m = re.match(r"open (.+)", cmd)
            if m:
                recep = m.group(1).strip()
                if "you open" in obs or "is open" in obs or "already open" in obs:
                    self.is_open.add(recep)
            self._parse_visible_objects(obs)

        elif cmd.startswith("close "):
            m = re.match(r"close (.+)", cmd)
            if m:
                self.is_open.discard(m.group(1).strip())

        elif cmd.startswith("clean "):
            m = re.match(r"clean (.+?) with ", cmd)
            if m and "clean" in obs:
                self.cleaned.add(m.group(1).strip())

        elif cmd.startswith("heat "):
            m = re.match(r"heat (.+?) with ", cmd)
            if m and any(w in obs for w in ("heat", "hot", "warm")):
                obj = m.group(1).strip()
                self.heated.add(obj)
                self.cooled.discard(obj)

        elif cmd.startswith("cool "):
            m = re.match(r"cool (.+?) with ", cmd)
            if m and any(w in obs for w in ("cool", "cold", "chill")):
                obj = m.group(1).strip()
                self.cooled.add(obj)
                self.heated.discard(obj)

        elif cmd.startswith("slice "):
            m = re.match(r"slice (.+?) with ", cmd)
            if m and "slice" in obs:
                self.sliced.add(m.group(1).strip())

        elif cmd.startswith("go to ") or cmd.startswith("examine "):
            self._parse_visible_objects(obs)

    def _parse_visible_objects(self, obs: str) -> None:
        """'On the countertop 1, you see a mug 1, a cup 2' → update self.at."""
        for m in re.finditer(
            r"on the ([a-z]+(?:\s+[a-z]+)?\s+\d+)[,.].*?you see (.*?)(?=\.|$)", obs
        ):
            recep = _base(m.group(1))
            for item_m in re.finditer(
                r"\b(?:a|an) ([a-z]+(?:\s+[a-z]+)?\s+\d+)\b", m.group(2)
            ):
                obj = item_m.group(1).strip()
                if self.at.get(obj) != "held":  # held status takes priority
                    self.at[obj] = recep

    # ── judge ─────────────────────────────────────────────────────────────────

    def judge(self, task: str) -> bool:
        """Return True if ShadowState satisfies the task conditions.

        Handles: put X in Y, put two X in Y, clean/heat/cool X then place,
                 examine X under desklamp.
        Returns False for unknown task patterns (conservative).
        """
        t = _norm(task)
        t = re.sub(r"^your task is to:?\s*", "", t)

        # ── put two X in/on Y ──────────────────────────────────────────────
        m = re.match(r"put two (\w+?)s? (?:in|on) (?:a |the )?(.+)", t)
        if m:
            obj_type, dst = m.group(1), _base(m.group(2))
            n = sum(1 for o, l in self.at.items() if _base(o) == obj_type and l == dst)
            return n >= 2

        # ── clean → place ──────────────────────────────────────────────────
        m = re.match(r"clean (?:some |a )?(\w+) and put it (?:in|on) (?:a |the )?(.+)", t)
        if m:
            obj_type, dst = m.group(1), _base(m.group(2))
            return any(
                _base(o) == obj_type and l == dst and o in self.cleaned
                for o, l in self.at.items()
            )

        # ── heat → place ───────────────────────────────────────────────────
        m = re.match(r"heat (?:some |a )?(\w+) and put it (?:in|on) (?:a |the )?(.+)", t)
        if m:
            obj_type, dst = m.group(1), _base(m.group(2))
            return any(
                _base(o) == obj_type and l == dst and o in self.heated
                for o, l in self.at.items()
            )

        # ── cool → place ───────────────────────────────────────────────────
        m = re.match(r"cool (?:some |a )?(\w+) and put it (?:in|on) (?:a |the )?(.+)", t)
        if m:
            obj_type, dst = m.group(1), _base(m.group(2))
            return any(
                _base(o) == obj_type and l == dst and o in self.cooled
                for o, l in self.at.items()
            )

        # ── examine under desklamp ─────────────────────────────────────────
        m = re.match(r"(?:look at|examine) (?:the |a )?(\w+)(?:\s+\d+)? (?:under|with) (?:the )?desklamp", t)
        if m:
            obj_type = m.group(1)
            # Approximate: holding the right object type
            return self.holding is not None and _base(self.holding) == obj_type

        # ── simple place ───────────────────────────────────────────────────
        m = re.match(r"put (?:some |a )?(\w+)(?:\s+\d+)? (?:in|on) (?:a |the )?(.+)", t)
        if m:
            obj_type, dst = m.group(1), _base(m.group(2))
            return any(
                _base(o) == obj_type and l == dst
                for o, l in self.at.items()
            )

        return False  # unknown task pattern → conservative false

    # ── serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "at": self.at,
            "holding": self.holding,
            "is_open": sorted(self.is_open),
            "cleaned": sorted(self.cleaned),
            "heated": sorted(self.heated),
            "cooled": sorted(self.cooled),
            "sliced": sorted(self.sliced),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ShadowState":
        s = cls()
        s.at = d.get("at", {})
        s.holding = d.get("holding")
        s.is_open = set(d.get("is_open", []))
        s.cleaned = set(d.get("cleaned", []))
        s.heated = set(d.get("heated", []))
        s.cooled = set(d.get("cooled", []))
        s.sliced = set(d.get("sliced", []))
        return s
