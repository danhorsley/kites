"""kites prototype.

Milestone 1: rendered tessellation, click-to-flood-fill. (done, readable)
Milestone 2: hover previews + click commits a match (rule #1, segments only).
Milestone 3 (current): segment gravity + auto-cascade. After a match, empty
    segments are filled by colors falling "down" through the triangular
    sub-lattice; top-of-board empties spawn new random colors; any new ≥M
    groups created by gravity auto-clear and re-cascade.

Controls:
    hover        preview the connected same-color group under the cursor
    left click   if preview is big enough (>= M_MIN), clear + cascade
    R            regenerate the board
    ESC / close  quit
"""

import random
from collections import deque

import pygame


# --- Board geometry ---------------------------------------------------------
#
# Rhombuses are indexed by (a, b) on a "checkerboard" lattice: only cells
# where (a + b) is even are valid. Neighbor rhombuses are offset by
# (+-1, +-1). Each rhombus has vertical and horizontal diagonals; the center
# of rhombus (a, b) is at:
#
#     cx = ORIGIN_X + a * (W / 2) + W / 2
#     cy = ORIGIN_Y + b * (H / 2) + H / 2
#
# Its vertices are (cx, cy +- H/2) and (cx +- W/2, cy).

GRID_W = 9
GRID_H = 9
RHOMBUS_W = 80
RHOMBUS_H = 120
ORIGIN_X = 40
ORIGIN_Y = 40

SCREEN_W = ORIGIN_X * 2 + (GRID_W + 1) * RHOMBUS_W // 2
SCREEN_H = ORIGIN_Y * 2 + (GRID_H + 1) * RHOMBUS_H // 2

# Segment indices, clockwise from NE. A segment sits in one quadrant relative
# to the kite's center and owns one of the kite's four outer edges.
SEG_NE, SEG_SE, SEG_SW, SEG_NW = 0, 1, 2, 3

# Intra-kite adjacency. Each segment shares a diagonal edge with the two
# segments beside it; it meets the opposite segment only at the center point
# and so is NOT adjacent to it.
INTRA_NEIGHBORS = {
    SEG_NE: (SEG_NW, SEG_SE),
    SEG_SE: (SEG_NE, SEG_SW),
    SEG_SW: (SEG_SE, SEG_NW),
    SEG_NW: (SEG_SW, SEG_NE),
}

# Inter-kite adjacency. A segment's outer edge is shared with one segment in
# one neighboring kite.
#   seg -> (kite offset (da, db), opposite seg in that kite)
INTER_NEIGHBOR = {
    SEG_NE: ((1, -1), SEG_SW),
    SEG_SE: ((1, 1), SEG_NW),
    SEG_SW: ((-1, 1), SEG_NE),
    SEG_NW: ((-1, -1), SEG_SE),
}

# Gravity: for each segment, which of its 3 edge-neighbors sits visually above
# it (i.e., has the lowest y-centroid). When a segment is empty, it pulls its
# color from this neighbor. Chains of "above" strictly decrease y, so no cycles
# — every chain eventually walks off the top of the board into "sky", where a
# new random color is spawned.
#
# Derived from triangle centroid analysis:
#   NE centroid (+W/6, -H/6), SE (+W/6, +H/6), SW (-W/6, +H/6), NW (-W/6, -H/6).
# The above-neighbor of an "upper" segment (NE, NW) is in a different kite
# (up-right / up-left). The above-neighbor of a "lower" segment (SE, SW) is
# an intra-kite segment in the same kite.
ABOVE = {
    SEG_NE: ((1, -1), SEG_SW),
    SEG_NW: ((-1, -1), SEG_SE),
    SEG_SE: ((0, 0), SEG_NE),
    SEG_SW: ((0, 0), SEG_NW),
}


# --- Rules ------------------------------------------------------------------

M_MIN = 3          # minimum group size to count as a match
EMPTY = None       # segment color value meaning "cleared"
MAX_CASCADE = 1    # max auto-cascade waves after a manual click. 0 disables
                   # cascades entirely. Higher values let chains run longer,
                   # but note: cascades ALWAYS terminate in an unmatched state
                   # (otherwise they wouldn't terminate), so unlimited cascade
                   # drains the board on every click.


# --- Colors -----------------------------------------------------------------

COLORS = [
    (220, 80, 80),    # red
    (80, 150, 220),   # blue
    (240, 200, 90),   # yellow
    (100, 180, 110),  # green
]

BG = (28, 28, 34)
HOLE = (18, 18, 22)                # cleared segment fill
KITE_EDGE = (15, 15, 20)
SEG_EDGE = (45, 45, 55)
PREVIEW_MATCH = (255, 255, 255)    # highlight when group is matchable
PREVIEW_DIM = (110, 110, 125)      # highlight when group is too small
TEXT = (200, 200, 210)


# --- Geometry helpers -------------------------------------------------------

def is_valid_cell(a, b):
    return 0 <= a < GRID_W and 0 <= b < GRID_H and (a + b) % 2 == 0


def cell_center(a, b):
    cx = ORIGIN_X + a * (RHOMBUS_W / 2) + RHOMBUS_W / 2
    cy = ORIGIN_Y + b * (RHOMBUS_H / 2) + RHOMBUS_H / 2
    return cx, cy


def rhombus_vertices(a, b):
    cx, cy = cell_center(a, b)
    hw = RHOMBUS_W / 2
    hh = RHOMBUS_H / 2
    # top, right, bottom, left
    return [(cx, cy - hh), (cx + hw, cy), (cx, cy + hh), (cx - hw, cy)]


def segment_triangle(a, b, seg):
    """Return the 3 vertices of one triangular segment."""
    cx, cy = cell_center(a, b)
    hw = RHOMBUS_W / 2
    hh = RHOMBUS_H / 2
    top = (cx, cy - hh)
    right = (cx + hw, cy)
    bottom = (cx, cy + hh)
    left = (cx - hw, cy)
    center = (cx, cy)
    if seg == SEG_NE:
        return [center, top, right]
    if seg == SEG_SE:
        return [center, right, bottom]
    if seg == SEG_SW:
        return [center, bottom, left]
    return [center, left, top]  # SEG_NW


def point_in_rhombus(px, py, a, b):
    cx, cy = cell_center(a, b)
    return abs(px - cx) / (RHOMBUS_W / 2) + abs(py - cy) / (RHOMBUS_H / 2) <= 1


def segment_of_point(px, py, a, b):
    """Given a point known to be inside kite (a, b), return which segment."""
    cx, cy = cell_center(a, b)
    dx = px - cx
    dy = py - cy
    if dy <= 0:
        return SEG_NE if dx >= 0 else SEG_NW
    return SEG_SE if dx >= 0 else SEG_SW


def find_segment(px, py):
    """Return (a, b, seg) for a screen-space point, or None."""
    for b in range(GRID_H):
        for a in range(GRID_W):
            if is_valid_cell(a, b) and point_in_rhombus(px, py, a, b):
                return a, b, segment_of_point(px, py, a, b)
    return None


def neighbors(a, b, seg):
    """Yield all segment-adjacent (a, b, seg) triples."""
    for nseg in INTRA_NEIGHBORS[seg]:
        yield a, b, nseg
    (da, db), nseg = INTER_NEIGHBOR[seg]
    na, nb = a + da, b + db
    if is_valid_cell(na, nb):
        yield na, nb, nseg


# --- Board state ------------------------------------------------------------

def make_board():
    """Assign a random color (0..len(COLORS)-1) to each of the 4 segments."""
    return {
        (a, b): [random.randrange(len(COLORS)) for _ in range(4)]
        for b in range(GRID_H)
        for a in range(GRID_W)
        if is_valid_cell(a, b)
    }


def flood_fill(board, start):
    """BFS on the segment-adjacency graph, same color only.

    Empty (cleared) segments are not part of any group.
    """
    a, b, seg = start
    color = board[(a, b)][seg]
    if color is EMPTY:
        return set()
    group = set()
    queue = deque([start])
    while queue:
        node = queue.popleft()
        if node in group:
            continue
        na, nb, nseg = node
        if board[(na, nb)][nseg] != color:
            continue
        group.add(node)
        for nxt in neighbors(na, nb, nseg):
            if nxt not in group:
                queue.append(nxt)
    return group


def apply_gravity(board):
    """Pull colors down into empty segments and refill the top from sky.

    Returns the set of (a, b, seg) positions that received a new color during
    this pass — these are the "newly placed" tiles used to qualify cascades.
    """
    newly_placed = set()
    changed = True
    while changed:
        changed = False
        for (a, b) in board:
            for seg in range(4):
                if board[(a, b)][seg] is not EMPTY:
                    continue
                (da, db), nseg = ABOVE[seg]
                na, nb = a + da, b + db
                if is_valid_cell(na, nb):
                    src = board[(na, nb)][nseg]
                    if src is not EMPTY:
                        board[(a, b)][seg] = src
                        board[(na, nb)][nseg] = EMPTY
                        newly_placed.add((a, b, seg))
                        changed = True
                else:
                    board[(a, b)][seg] = random.randrange(len(COLORS))
                    newly_placed.add((a, b, seg))
                    changed = True
    return newly_placed


def new_matches(board, newly_placed):
    """Groups of size >= M_MIN that include at least one newly-placed tile.

    Latent groups formed from tiles that didn't move in the last gravity pass
    are NOT returned — they wait for the player to click them manually.
    """
    visited = set()
    groups = []
    for node in newly_placed:
        if node in visited:
            continue
        a, b, seg = node
        if board[(a, b)][seg] is EMPTY:
            continue
        group = flood_fill(board, node)
        visited |= group
        if len(group) >= M_MIN:
            groups.append(group)
    return groups


def resolve_cascades(board, max_depth=MAX_CASCADE):
    """Settle the board after a manual match.

    Apply gravity, and up to `max_depth` times, auto-clear any new ≥M groups
    created by the fall. "New" = contains at least one tile placed during the
    most recent gravity pass. Latent groups (untouched by the fall) persist.

    Returns (extra_matches_cleared, cascade_depth).
    """
    newly_placed = apply_gravity(board)
    extra = 0
    depth = 0
    while depth < max_depth:
        groups = new_matches(board, newly_placed)
        if not groups:
            break
        depth += 1
        for g in groups:
            extra += 1
            for a, b, seg in g:
                board[(a, b)][seg] = EMPTY
        newly_placed = apply_gravity(board)
    return extra, depth


# --- Rendering --------------------------------------------------------------

def draw(screen, font, board, preview, match_count, last_cascade):
    screen.fill(BG)

    for (a, b), segs in board.items():
        for seg in range(4):
            tri = segment_triangle(a, b, seg)
            fill = HOLE if segs[seg] is EMPTY else COLORS[segs[seg]]
            pygame.draw.polygon(screen, fill, tri)
            pygame.draw.polygon(screen, SEG_EDGE, tri, 1)

    for (a, b) in board:
        pygame.draw.polygon(screen, KITE_EDGE, rhombus_vertices(a, b), 2)

    matchable = len(preview) >= M_MIN
    hl_color = PREVIEW_MATCH if matchable else PREVIEW_DIM
    hl_width = 3 if matchable else 2
    for (a, b, seg) in preview:
        pygame.draw.polygon(screen, hl_color, segment_triangle(a, b, seg), hl_width)

    if preview:
        action = "click to clear" if matchable else f"need {M_MIN}+"
        status = f"group: {len(preview)}  ({action})"
    else:
        status = "hover a segment"
    status += f"    matches: {match_count}"
    if last_cascade[0] or last_cascade[1]:
        status += f"    last: +{last_cascade[0]} cascaded (depth {last_cascade[1]})"
    screen.blit(font.render(status, True, TEXT), (10, SCREEN_H - 24))


# --- Main loop --------------------------------------------------------------

def preview_at(board, pos):
    hit = find_segment(*pos)
    return flood_fill(board, hit) if hit else set()


def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("kites — prototype")
    font = pygame.font.SysFont(None, 20)
    clock = pygame.time.Clock()

    board = make_board()
    preview = set()
    match_count = 0
    last_cascade = (0, 0)  # (extra_matches, depth) from most recent click
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_r:
                    board = make_board()
                    match_count = 0
                    last_cascade = (0, 0)
                    preview = preview_at(board, pygame.mouse.get_pos())
            elif event.type == pygame.MOUSEMOTION:
                preview = preview_at(board, event.pos)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if len(preview) >= M_MIN:
                    for a, b, seg in preview:
                        board[(a, b)][seg] = EMPTY
                    match_count += 1
                    extra, depth = resolve_cascades(board)
                    match_count += extra
                    last_cascade = (extra, depth)
                    preview = preview_at(board, event.pos)

        draw(screen, font, board, preview, match_count, last_cascade)
        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


if __name__ == "__main__":
    main()
