# kites

Color-segment matching puzzle on a kite tessellation

Overview Kites is a casual match-3+ puzzle game where the board is tiled with colorful kites. Each kite is divided into 4 triangular segments (by its diagonals), each painted with one of N colors. Players match M or more adjacent same-color segments; any kite containing a matched segment is removed. Clear the board or reach score targets before time/moves run out.Unique hook: Geometric kite tiling creates interesting adjacency patterns (intra-kite center + inter-kite edges).Core GameplayBoard: Infinite or finite grid of convex kites (e.g., 60-90-120-90 or rhombus kites for simplicity).
Input: Tap/drag to select chains of adjacent same-color segments.
Match Rule: M+ connected segments of the same color → remove every kite that touches any matched segment.
Mechanics:Optional gravity/falling: segments or new kites drop in OR select new piece from sidebar for a more relaxed experience
Chain reactions on new adjacencies - though cascades may not work well without gravity which we are not sure we want
Special clears (e.g., all-4 segments on one kite = bonus).

Win/Lose: Score-based levels, endless mode, or clear-board challenges - playtest to see what works

