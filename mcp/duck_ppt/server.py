"""
PowerPoint MCP Server v4 — Template-first, UI/UX focused.
Built to produce professional slides that USE the template correctly.
"""
import os, re, json
import win32com.client
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from typing import List, Dict, Optional, Any

# Configuração do Workspace
WORKSPACE_DIR = Path(os.getenv("WORKSPACE_DIR", os.getcwd())).resolve()
try:
    os.chdir(WORKSPACE_DIR)
except Exception as e:
    pass

mcp = FastMCP("PowerPoint MCP")

# ── VBA Constants ─────────────────────────────────────────────────────────────
ppAlignLeft, ppAlignCenter, ppAlignRight, ppAlignJustify = 1, 2, 3, 4
msoTrue, msoFalse = -1, 0
msoTextOrientationHorizontal = 1
msoAutoSizeTextToFitShape, msoAutoSizeShapeToFitText, msoAutoSizeNone = 2, 1, 0
msoGroup, msoPlaceholder, msoTextBox, msoPicture = 6, 14, 17, 3
msoAnchorTop, msoAnchorMiddle, msoAnchorBottom = 1, 3, 4
msoBringToFront, msoSendToBack, msoBringForward, msoSendBackward = 0, 1, 2, 3

SHAPE_TYPES = {
    "rectangle": 1, "rounded_rectangle": 5, "oval": 9, "diamond": 4,
    "parallelogram": 25, "pentagon": 56, "hexagon": 57,
    "arrow_right": 13, "arrow_left": 14,
    "star_4": 58, "star_5": 92, "star_8": 60,
    "chevron": 52, "trapezoid": 3, "bevel": 15,
    "callout_rect": 61, "callout_rounded": 62,
}

SLIDE_W, SLIDE_H = 960, 540  # points, widescreen 16:9


# ── Internal helpers ─────────────────────────────────────────────────────────

def _app():
    app = win32com.client.Dispatch("PowerPoint.Application")
    app.Visible = msoTrue
    return app

def _prs():
    app = _app()
    if app.Presentations.Count == 0:
        raise ValueError("No active presentation.")
    return app.ActivePresentation

def _slide(prs, idx):
    if not 1 <= idx <= prs.Slides.Count:
        raise ValueError(f"Slide {idx} does not exist (total: {prs.Slides.Count})")
    return prs.Slides(idx)

def _find(slide, ident):
    s = str(ident)
    for i in range(1, slide.Shapes.Count + 1):
        sh = slide.Shapes(i)
        if str(sh.Id) == s or sh.Name == s:
            return sh
        if sh.Type == msoGroup:
            for j in range(1, sh.GroupItems.Count + 1):
                sub = sh.GroupItems(j)
                if str(sub.Id) == s or sub.Name == s:
                    return sub
    return None

def _hex(h):
    h = h.lstrip("#")
    if len(h) == 3: h = h[0]*2+h[1]*2+h[2]*2
    return int(h[:2],16), int(h[2:4],16), int(h[4:6],16)

def _vba(r,g,b): return r + g*256 + b*65536


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — DESIGN BRIEF (call first)
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def get_design_brief() -> str:
    """CALL THIS BEFORE STARTING any presentation.
    Returns the complete workflow, design rules, and layout recipes for
    producing professional slides that correctly USE the template.
    """
    return r"""
# POWERPOINT MCP — DESIGN BRIEF v4

## THE GOLDEN RULE: USE THE TEMPLATE, DON'T FIGHT IT

The template already has backgrounds, fonts, colors, and logo placement.
Your job is to ADD content ON TOP of what the template provides — NOT replace it.

### What "using the template" means:
1. `scan_template()` — understand every existing shape, image, and element in the file.
2. `duplicate_slide(N)` — always clone the most similar existing slide, never add blank ones.
3. `get_slide_info(N)` — read the duplicated slide's shape IDs before touching anything.
4. Edit ONLY the text content shapes. Leave background shapes, images, and logos ALONE.
5. If you must add decorative shapes, only ADD them; never move/resize template shapes.

### What destroys presentations:
- Adding a full-size dark rectangle over everything (buries the template background)
- Using `set_slide_background()` when the template already has a gradient/image background
- Ignoring template shapes and building slides from scratch
- Leaving slides from Google Slides imports with "Google Shape" names (delete them)
- Duplicating the wrong slide and not cleaning up its leftover content

---

## SLIDE CANVAS
- Widescreen 16:9 → **960 × 540 pt** (EMU: 12192000 × 6858000)
- Safe content margin: **40 pt** from all edges
- Never place text at x < 40 or x > 920

## TYPOGRAPHY (match the template's fonts)
| Role         | Size  | Weight | Color      |
|--------------|-------|--------|------------|
| Cover title  | 44 pt | bold   | #FFFFFF    |
| Slide title  | 36 pt | bold   | #000000 or #FFFFFF depending on bg |
| Section head | 22 pt | bold   | template accent |
| Body text    | 16 pt | normal | #333333    |
| Caption/small| 14 pt | normal | #666666    |
| KPI number   | 60 pt | bold   | #FFFFFF    |
**NEVER below 13 pt. NEVER.**

## COLOR PALETTE (always inspect_template_colors first)
- Use only colors already in the template
- Common Claro/AeC palette: #E3000B (red), #FFFFFF, #000000, #333333, #7EC8E3 (light blue), #1E2761 (navy)

---

## STEP-BY-STEP WORKFLOW

### Step 1 — Understand the template
```
scan_template()           → full map of all slides, shapes, images
inspect_template_colors() → hex palette
list_slide_layouts()      → available layout options
```

### Step 2 — Plan slide structure
For each content slide, identify the MOST SIMILAR template slide to clone.
Never create blank slides if a suitable template slide exists.

### Step 3 — Build each slide
```
duplicate_slide(best_match_index)  → returns new slide index
get_slide_info(new_index)          → shows all shape IDs and positions
# ONLY edit text shapes — check which are content vs. decorative
update_shape_text(N, "ShapeID", "new text")
# If a slide has leftover "Google Shape" elements, delete them:
delete_shape(N, "Google Shape;302;p34")
```

### Step 4 — Add NEW content if needed (cards, stats, etc.)
```
# Add shapes ON TOP of template, don't replace it
add_shape("rounded_rectangle", ...)   → card background
add_textbox(...)                       → card content
send_shape_to_back(N, shape_id)       → if it's a background panel
```

### Step 5 — Quality check
```
audit_presentation()        → finds overlaps, tiny fonts, out-of-bounds
smart_layout_vertical(N)    → fixes overlapping text stacks
cleanup_unused_slides()     → removes placeholder slides
```

### Step 6 — Save
```
save_presentation("C:/path/output.pptx")
```

---

## LAYOUT RECIPES

### Recipe A — Title Slide (clone slide 1)
Keep the gradient blob image and red line. Only update:
- "Retângulo 5" → main title text (44pt bold white)
- "Retângulo 7" → subtitle text (22pt light blue)

### Recipe B — Content Slide with 4 Cards (clone a card-style slide)
Template already has rounded-rect card structure.
Just update each card's header text box and body text box.

### Recipe C — Stat/KPI Slide (clone stat slide)
Three columns with big numbers. Update the number and label text boxes.

### Recipe D — Full Dark Slide (clone dark slide)
If template has a dark slide, clone it. Update title and body only.

### Recipe E — Timeline (clone timeline slide)
Update year labels and event text boxes. Don't move the dots/line shapes.

---

## COMMON MISTAKES TO AVOID
- ❌ add_shape("rectangle", 0, 0, 960, 540) — this paints over everything
- ❌ set_slide_background() on slides that already have template images
- ❌ Leaving Google Shapes from imported content (delete them all)
- ❌ Adding new text boxes when you could just update existing template ones
- ❌ Using font sizes above 44pt for body content (only KPI stats can be 60pt)
- ❌ Not calling get_slide_info() before editing (you'll edit wrong shapes)
"""


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — TEMPLATE SCANNING & DISCOVERY
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def scan_template() -> str:
    """Deep scan of the active presentation.
    Returns every slide with ALL shapes: ID, name, type, position, fill color, font size, text.
    Also flags:
    - 'Google Shape' imports that should be deleted
    - Shapes outside canvas bounds (x < 0 or x+w > 970)
    - Fonts below 13pt

    Call this FIRST to understand the full template structure before editing.
    """
    try:
        prs = _prs()
        out = [f"TEMPLATE SCAN — {prs.Slides.Count} slides  ({SLIDE_W}×{SLIDE_H} pt)\n"]
        type_map = {14:"Placeholder",6:"Group",1:"AutoShape",17:"TextBox",3:"Picture",13:"Table"}

        for i in range(1, prs.Slides.Count + 1):
            slide = prs.Slides(i)
            out.append(f"\n── SLIDE {i} ── [{slide.Shapes.Count} shapes]")

            for j in range(1, slide.Shapes.Count + 1):
                sh = slide.Shapes(j)
                t = type_map.get(sh.Type, f"T{sh.Type}")
                L,T,W,H = sh.Left, sh.Top, sh.Width, sh.Height

                flags = []
                if "Google Shape" in sh.Name:
                    flags.append("⚠ GOOGLE-IMPORT — consider deleting")
                if L < -5 or L+W > SLIDE_W+5:
                    flags.append("⚠ OUT-OF-BOUNDS")

                line = f"  [{t}] ID:{sh.Id} '{sh.Name}'  L:{L:.0f} T:{T:.0f} W:{W:.0f} H:{H:.0f}"

                # Fill
                try:
                    f = sh.Fill
                    if f.Type == 1:
                        v = f.ForeColor.RGB
                        r,g,b = v&0xFF,(v>>8)&0xFF,(v>>16)&0xFF
                        line += f"  fill:#{r:02X}{g:02X}{b:02X}"
                except: pass

                # Text
                if sh.HasTextFrame:
                    txt = sh.TextFrame.TextRange.Text.replace("\r"," ").replace("\n","↵")[:60]
                    try:
                        fs = sh.TextFrame.TextRange.Font.Size
                        if 0 < fs < 13: flags.append(f"⚠ TINY {fs:.0f}pt")
                        line += f"  {fs:.0f}pt  \"{txt}\""
                    except:
                        line += f"  \"{txt}\""

                if flags:
                    line += "  " + " ".join(flags)
                out.append(line)

                # Group children
                if sh.Type == msoGroup:
                    for k in range(1, sh.GroupItems.Count + 1):
                        sub = sh.GroupItems(k)
                        sl = f"    ↳[{type_map.get(sub.Type,f'T{sub.Type}')}] ID:{sub.Id} '{sub.Name}'  L:{sub.Left:.0f} T:{sub.Top:.0f} W:{sub.Width:.0f} H:{sub.Height:.0f}"
                        if sub.HasTextFrame:
                            txt2 = sub.TextFrame.TextRange.Text.replace("\r"," ")[:50]
                            try:
                                fs2 = sub.TextFrame.TextRange.Font.Size
                                sl += f"  {fs2:.0f}pt  \"{txt2}\""
                            except:
                                sl += f"  \"{txt2}\""
                        out.append(sl)

        return "\n".join(out)
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def get_slide_info(slide_index: int) -> str:
    """Detailed shape map for one slide.
    Shows ID, name, position, size, fill, font size, and text for every shape.
    Flags out-of-bounds elements and tiny fonts.
    Always call this BEFORE editing a slide to know the correct shape IDs.
    """
    try:
        prs = _prs()
        slide = _slide(prs, slide_index)
        type_map = {14:"Placeholder",6:"Group",1:"AutoShape",17:"TextBox",3:"Picture",13:"Table"}
        out = [f"SLIDE {slide_index}  [{slide.Shapes.Count} shapes  {SLIDE_W}×{SLIDE_H} pt]"]

        # bg
        try:
            bg = slide.Background.Fill
            if bg.Type == 1:
                v = bg.ForeColor.RGB
                r,g,b = v&0xFF,(v>>8)&0xFF,(v>>16)&0xFF
                out.append(f"  bg-color: #{r:02X}{g:02X}{b:02X}")
        except: pass

        def row(sh, pre=""):
            t = type_map.get(sh.Type, f"T{sh.Type}")
            L,T,W,H = sh.Left,sh.Top,sh.Width,sh.Height
            flags = []
            if "Google Shape" in sh.Name: flags.append("⚠GOOGLE")
            if L < -5 or L+W > SLIDE_W+5: flags.append("⚠OOB")
            s = f"{pre}[{t}] ID:{sh.Id} '{sh.Name}'  L:{L:.0f} T:{T:.0f} W:{W:.0f} H:{H:.0f}"
            try:
                f = sh.Fill
                if f.Type == 1:
                    v = f.ForeColor.RGB
                    r,g,b=v&0xFF,(v>>8)&0xFF,(v>>16)&0xFF
                    s += f"  fill:#{r:02X}{g:02X}{b:02X}"
            except: pass
            if sh.HasTextFrame:
                txt = sh.TextFrame.TextRange.Text.replace("\r"," ").replace("\n","↵")[:70]
                try:
                    fs = sh.TextFrame.TextRange.Font.Size
                    if 0 < fs < 13: flags.append(f"⚠TINY{fs:.0f}pt")
                    s += f"  {fs:.0f}pt  \"{txt}\""
                except:
                    s += f"  \"{txt}\""
            if flags: s += "  "+" ".join(flags)
            return s

        for i in range(1, slide.Shapes.Count + 1):
            sh = slide.Shapes(i)
            out.append(row(sh, "  "))
            if sh.Type == msoGroup:
                for j in range(1, sh.GroupItems.Count + 1):
                    out.append(row(sh.GroupItems(j), "    ↳ "))

        return "\n".join(out)
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def inspect_template_colors() -> str:
    """Return the theme color palette (hex codes) and font scheme.
    Call this to know which colors to use in fill_color, font color, etc.
    """
    try:
        prs = _prs()
        theme  = prs.Designs(1).SlideMaster.Theme
        clrs   = theme.ThemeColorScheme
        fonts  = theme.ThemeFontScheme
        names  = ["Background 1","Text 1","Background 2","Text 2",
                  "Accent 1","Accent 2","Accent 3","Accent 4",
                  "Accent 5","Accent 6","Hyperlink","Followed Hyperlink"]
        out = ["THEME COLORS"]
        for i,n in enumerate(names,1):
            try:
                v = clrs(i).RGB
                r,g,b=v&0xFF,(v>>8)&0xFF,(v>>16)&0xFF
                out.append(f"  {n}: #{r:02X}{g:02X}{b:02X}")
            except: out.append(f"  {n}: N/A")
        out.append("\nTHEME FONTS")
        for label, method in [("Headings","MajorFont"),("Body","MinorFont")]:
            try: out.append(f"  {label}: {getattr(fonts,method)('Latin').Name}")
            except: out.append(f"  {label}: N/A")
        return "\n".join(out)
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def get_presentation_info() -> str:
    """List all slides with index, title, and shape count.
    Use to plan which slides to duplicate or delete.
    """
    try:
        prs = _prs()
        total = prs.Slides.Count
        out = [f"Total slides: {total}"]
        for i in range(1, total+1):
            sl = prs.Slides(i)
            title = "[no title]"
            if sl.Shapes.HasTitle:
                title = sl.Shapes.Title.TextFrame.TextRange.Text.strip().replace("\r"," ")[:60]
            else:
                for j in range(1, sl.Shapes.Count+1):
                    s = sl.Shapes(j)
                    if s.HasTextFrame and s.TextFrame.TextRange.Text.strip():
                        title = s.TextFrame.TextRange.Text.strip()[:60]
                        break
            out.append(f"  Slide {i:02d}: [{sl.Shapes.Count} shapes]  {title}")
        return "\n".join(out)
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def list_slide_layouts() -> str:
    """List all custom layouts in the template (index + name)."""
    try:
        prs = _prs()
        out = []
        for i in range(1, prs.Designs(1).SlideMaster.CustomLayouts.Count+1):
            lay = prs.Designs(1).SlideMaster.CustomLayouts(i)
            out.append(f"  {i}: '{lay.Name}'")
        return "\n".join(out) or "No layouts found."
    except Exception as e:
        return f"Error: {e}"


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — PRESENTATION & SLIDE MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def list_templates() -> List[str]:
    """List .pptx/.potx/.thmx files in the templates/ directory."""
    try:
        d = os.path.join(os.path.dirname(__file__), "templates")
        os.makedirs(d, exist_ok=True)
        return [f for f in os.listdir(d) if f.endswith((".pptx",".potx",".thmx"))]
    except Exception as e:
        return [f"Error: {e}"]


@mcp.tool()
def create_presentation(template_name: str) -> str:
    """Open a template file as a new untitled presentation."""
    try:
        d = os.path.join(os.path.dirname(__file__), "templates")
        path = os.path.abspath(os.path.join(d, template_name))
        if not os.path.exists(path):
            return f"Template '{template_name}' not found."
        _app().Presentations.Open(path, ReadOnly=0, Untitled=msoTrue, WithWindow=msoTrue)
        return f"Opened template '{template_name}'."
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def open_presentation(file_path: str) -> str:
    """Open an existing .pptx file for editing."""
    try:
        file_path = str(Path(file_path).resolve())
        if not os.path.exists(file_path):
            return f"File not found: {file_path}"
        _app().Presentations.Open(file_path, ReadOnly=0, Untitled=msoFalse, WithWindow=msoTrue)
        return f"Opened: {file_path}"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def duplicate_slide(slide_index: int) -> str:
    """Clone a slide, preserving ALL template graphics, colors, images, and layout.
    ALWAYS prefer this over add_slide_from_layout() to keep template visuals.
    Returns the new slide's index.
    """
    try:
        prs = _prs()
        if not 1 <= slide_index <= prs.Slides.Count:
            return f"Slide {slide_index} does not exist."
        r = prs.Slides(slide_index).Duplicate()
        new_idx = r.Item(1).SlideIndex
        return f"Slide {slide_index} cloned → new slide {new_idx}. Now call get_slide_info({new_idx}) to see its shapes."
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def add_slide_from_layout(layout_index: int) -> str:
    """Add a blank slide using a template layout. Use duplicate_slide() instead when possible."""
    try:
        prs = _prs()
        idx = prs.Slides.Count + 1
        lay = prs.Designs(1).SlideMaster.CustomLayouts(layout_index)
        prs.Slides.AddSlide(idx, lay)
        return f"Slide {idx} added with layout '{lay.Name}'."
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def delete_slide(slide_index: int) -> str:
    """Delete a slide by index."""
    try:
        prs = _prs()
        _slide(prs, slide_index).Delete()
        return f"Slide {slide_index} deleted."
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def reorder_slide(slide_index: int, new_position: int) -> str:
    """Move a slide to a new position."""
    try:
        prs = _prs()
        total = prs.Slides.Count
        if not 1 <= slide_index <= total: return f"Slide {slide_index} invalid."
        if not 1 <= new_position <= total: return f"Position {new_position} invalid."
        prs.Slides(slide_index).MoveTo(new_position)
        return f"Slide {slide_index} → position {new_position}."
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def cleanup_unused_slides() -> str:
    """Delete slides still containing unedited placeholder text."""
    try:
        prs = _prs()
        kw = ["clique para","click to","lorem ipsum","título do slide",
              "texto aqui","[insira]","slide title","type here",
              "our   aim","the  goal","goals inside a company","an aim in a corporate"]
        deleted = 0
        for i in range(prs.Slides.Count, 0, -1):
            sl = prs.Slides(i)
            for j in range(1, sl.Shapes.Count+1):
                s = sl.Shapes(j)
                if s.HasTextFrame and any(k in s.TextFrame.TextRange.Text.lower() for k in kw):
                    sl.Delete(); deleted += 1; break
        return f"Removed {deleted} placeholder slide(s)."
    except Exception as e:
        return f"Error: {e}"


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — SHAPE TEXT EDITING (primary editing tools)
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def update_shape_text(slide_index: int, shape_identifier: str, new_text: str) -> str:
    """Replace the text of a shape while PRESERVING its existing font, size, and color.
    This is the safest way to edit template shapes — it changes only the words,
    not the visual style.
    Use get_slide_info() first to find shape IDs.
    """
    try:
        prs = _prs()
        slide = _slide(prs, slide_index)
        sh = _find(slide, shape_identifier)
        if not sh or not sh.HasTextFrame:
            return f"Shape '{shape_identifier}' not found or has no text."
        # Preserve first run's formatting by setting text on the TextRange
        sh.TextFrame.TextRange.Text = new_text
        return f"Text updated: slide {slide_index} '{shape_identifier}' → \"{new_text[:50]}\""
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def update_shape_text_styled(
    slide_index: int,
    shape_identifier: str,
    new_text: str,
    font_size: float = None,
    bold: bool = None,
    color: str = None,
    alignment: int = None,
    font_name: str = None
) -> str:
    """Replace text AND optionally update its styling.
    Only specify the style properties you want to change — others are preserved.
    color: hex e.g. "#FFFFFF". alignment: 1=Left 2=Center 3=Right.
    """
    try:
        prs = _prs()
        slide = _slide(prs, slide_index)
        sh = _find(slide, shape_identifier)
        if not sh or not sh.HasTextFrame:
            return f"Shape '{shape_identifier}' not found."
        tr = sh.TextFrame.TextRange
        tr.Text = new_text
        if font_size  is not None: tr.Font.Size  = font_size
        if bold       is not None: tr.Font.Bold  = msoTrue if bold else msoFalse
        if color      is not None:
            r,g,b = _hex(color); tr.Font.Color.RGB = _vba(r,g,b)
        if font_name  is not None: tr.Font.Name  = font_name
        if alignment  is not None: tr.ParagraphFormat.Alignment = alignment
        return f"Text+style updated: slide {slide_index} '{shape_identifier}'."
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def update_shape_text_rich(
    slide_index: int,
    shape_identifier: str,
    paragraphs: List[Dict[str, Any]]
) -> str:
    """Replace a shape's text with multi-paragraph rich content.
    Each dict: text(str), font_size(float), bold(bool), italic(bool),
    color(hex str), alignment(int 1-4), space_before(float), space_after(float).
    """
    try:
        prs = _prs()
        slide = _slide(prs, slide_index)
        sh = _find(slide, shape_identifier)
        if not sh or not sh.HasTextFrame:
            return f"Shape '{shape_identifier}' not found."
        tf = sh.TextFrame
        tf.TextRange.Text = ""
        for idx, pd in enumerate(paragraphs):
            txt = pd.get("text","")
            if idx == 0:
                para = tf.TextRange.Paragraphs(1); para.Text = txt
            else:
                tf.TextRange.InsertAfter("\r")
                para = tf.TextRange.Paragraphs(idx+1); para.Text = txt
            run = para.Runs(1) if para.Runs.Count > 0 else para
            if "font_size"    in pd: run.Font.Size  = pd["font_size"]
            if "bold"         in pd: run.Font.Bold  = msoTrue if pd["bold"]  else msoFalse
            if "italic"       in pd: run.Font.Italic= msoTrue if pd["italic"]else msoFalse
            if "color"        in pd:
                r,g,b=_hex(pd["color"]); run.Font.Color.RGB=_vba(r,g,b)
            if "alignment"    in pd: para.ParagraphFormat.Alignment   = pd["alignment"]
            if "space_before" in pd: para.ParagraphFormat.SpaceBefore = pd["space_before"]
            if "space_after"  in pd: para.ParagraphFormat.SpaceAfter  = pd["space_after"]
        return f"Rich text: slide {slide_index} '{shape_identifier}' ({len(paragraphs)} ¶)."
    except Exception as e:
        return f"Error: {e}"


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — SHAPE PROPERTIES (position, fill, font, border)
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def update_shape_position(
    slide_index: int, shape_identifier: str,
    left: float=None, top: float=None,
    width: float=None, height: float=None
) -> str:
    """Move or resize a shape. Only provide values you want to change (in points)."""
    try:
        prs = _prs()
        slide = _slide(prs, slide_index)
        sh = _find(slide, shape_identifier)
        if not sh: return f"Shape '{shape_identifier}' not found."
        changes = []
        if left   is not None: sh.Left  =left;  changes.append(f"L={left}")
        if top    is not None: sh.Top   =top;   changes.append(f"T={top}")
        if width  is not None: sh.Width =width; changes.append(f"W={width}")
        if height is not None: sh.Height=height;changes.append(f"H={height}")
        return f"'{shape_identifier}': {', '.join(changes)}." if changes else "No changes."
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def update_shape_fill(
    slide_index: int, shape_identifier: str,
    color: str=None, transparency: float=0.0, no_fill: bool=False
) -> str:
    """Change a shape's fill color. color: hex e.g. '#E3000B'. no_fill=True makes it transparent."""
    try:
        prs = _prs()
        slide = _slide(prs, slide_index)
        sh = _find(slide, shape_identifier)
        if not sh: return f"Shape '{shape_identifier}' not found."
        if no_fill: sh.Fill.Visible=msoFalse; return f"'{shape_identifier}' fill removed."
        if color:
            r,g,b=_hex(color)
            sh.Fill.Solid(); sh.Fill.ForeColor.RGB=_vba(r,g,b)
            sh.Fill.Transparency=transparency
            return f"'{shape_identifier}' fill={color}."
        return "No changes."
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def update_shape_font(
    slide_index: int, shape_identifier: str,
    font_size: float=None, bold: bool=None, italic: bool=None,
    color: str=None, font_name: str=None, alignment: int=None
) -> str:
    """Update font properties of a shape. Only provide values to change.
    color: hex. alignment: 1=L 2=C 3=R 4=J.
    """
    try:
        prs = _prs()
        slide = _slide(prs, slide_index)
        sh = _find(slide, shape_identifier)
        if not sh or not sh.HasTextFrame: return f"Shape '{shape_identifier}' not found or no text."
        tr = sh.TextFrame.TextRange; changes=[]
        if font_size  is not None: tr.Font.Size =font_size; changes.append(f"sz={font_size}")
        if bold       is not None: tr.Font.Bold =(msoTrue if bold  else msoFalse); changes.append(f"bold={bold}")
        if italic     is not None: tr.Font.Italic=(msoTrue if italic else msoFalse); changes.append(f"italic={italic}")
        if color      is not None: r,g,b=_hex(color); tr.Font.Color.RGB=_vba(r,g,b); changes.append(f"color={color}")
        if font_name  is not None: tr.Font.Name=font_name; changes.append(f"font={font_name}")
        if alignment  is not None: tr.ParagraphFormat.Alignment=alignment; changes.append(f"align={alignment}")
        return f"'{shape_identifier}': {', '.join(changes)}." if changes else "No changes."
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def update_shape_border(
    slide_index: int, shape_identifier: str,
    color: str=None, weight: float=None, visible: bool=True
) -> str:
    """Update a shape's border. color: hex. weight: pt. visible=False hides border."""
    try:
        prs = _prs()
        slide = _slide(prs, slide_index)
        sh = _find(slide, shape_identifier)
        if not sh: return f"Shape '{shape_identifier}' not found."
        if not visible: sh.Line.Visible=msoFalse; return f"'{shape_identifier}' border hidden."
        sh.Line.Visible=msoTrue
        if color: r,g,b=_hex(color); sh.Line.ForeColor.RGB=_vba(r,g,b)
        if weight is not None: sh.Line.Weight=weight
        return f"'{shape_identifier}' border updated."
    except Exception as e:
        return f"Error: {e}"


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — ADDING NEW SHAPES & CONTENT
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def add_shape(
    slide_index: int, shape_type: str,
    left: float, top: float, width: float, height: float,
    fill_color: str="#4472C4",
    border_color: str="", border_weight: float=0.0,
    text: str="", font_size: int=16, font_color: str="#FFFFFF",
    font_bold: bool=False, text_align: int=ppAlignCenter,
    transparency: float=0.0
) -> str:
    """Add a geometric shape. Returns the new shape's ID (use it for z-order, etc.).

    shape_type: rectangle, rounded_rectangle, oval, diamond, parallelogram,
      pentagon, hexagon, arrow_right, arrow_left, star_4, star_5, star_8,
      chevron, trapezoid, bevel, callout_rect, callout_rounded.

    IMPORTANT: After adding a background panel, call send_shape_to_back() with its ID.
    """
    try:
        prs = _prs()
        slide = _slide(prs, slide_index)
        enum = SHAPE_TYPES.get(shape_type.lower())
        if enum is None:
            return f"Unknown shape_type '{shape_type}'. Options: {', '.join(SHAPE_TYPES)}"
        sh = slide.Shapes.AddShape(enum, left, top, width, height)
        r,g,b=_hex(fill_color)
        sh.Fill.Solid(); sh.Fill.ForeColor.RGB=_vba(r,g,b)
        sh.Fill.Transparency=transparency
        if border_color and border_weight>0:
            r2,g2,b2=_hex(border_color)
            sh.Line.Visible=msoTrue; sh.Line.ForeColor.RGB=_vba(r2,g2,b2); sh.Line.Weight=border_weight
        else:
            sh.Line.Visible=msoFalse
        if text and sh.HasTextFrame:
            tr=sh.TextFrame.TextRange; tr.Text=text; tr.Font.Size=font_size
            tr.Font.Bold=msoTrue if font_bold else msoFalse
            fr,fg,fb=_hex(font_color); tr.Font.Color.RGB=_vba(fr,fg,fb)
            tr.ParagraphFormat.Alignment=text_align
            sh.TextFrame.VerticalAnchor=msoAnchorMiddle
            sh.TextFrame.WordWrap=msoTrue
        return f"Shape '{shape_type}' ID:{sh.Id} added to slide {slide_index} at ({left:.0f},{top:.0f}) {width:.0f}×{height:.0f} fill={fill_color}"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def add_textbox(
    slide_index: int, text: str,
    left: float, top: float, width: float, height: float,
    font_size: int=16, bold: bool=False, italic: bool=False,
    color: str="#000000", alignment: int=ppAlignLeft,
    font_name: str="", vertical_anchor: int=msoAnchorTop
) -> str:
    """Add a text box at absolute coordinates.
    Returns the new shape's ID.
    color: hex. alignment: 1=L 2=C 3=R 4=J.
    Always check bounds: left+width ≤ 920, top+height ≤ 500.
    """
    try:
        prs = _prs()
        slide = _slide(prs, slide_index)
        tb = slide.Shapes.AddTextbox(msoTextOrientationHorizontal, left, top, width, height)
        tr = tb.TextFrame.TextRange
        tr.Text=text; tr.Font.Size=font_size
        tr.Font.Bold=msoTrue if bold else msoFalse
        tr.Font.Italic=msoTrue if italic else msoFalse
        r,g,b=_hex(color); tr.Font.Color.RGB=_vba(r,g,b)
        if font_name: tr.Font.Name=font_name
        tr.ParagraphFormat.Alignment=alignment
        tb.TextFrame.VerticalAnchor=vertical_anchor
        tb.TextFrame.WordWrap=msoTrue
        return f"Textbox ID:{tb.Id} added slide {slide_index}: \"{text[:40]}\" at ({left:.0f},{top:.0f})"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def add_textbox_rich(
    slide_index: int,
    left: float, top: float, width: float, height: float,
    paragraphs: List[Dict[str, Any]]
) -> str:
    """Add a text box with multiple paragraphs, each with independent formatting.
    Each dict: text, font_size, bold, italic, color(hex), alignment(1-4), space_before, space_after.
    Returns the new shape's ID.
    """
    try:
        prs = _prs()
        slide = _slide(prs, slide_index)
        tb = slide.Shapes.AddTextbox(msoTextOrientationHorizontal, left, top, width, height)
        tf = tb.TextFrame; tf.WordWrap=msoTrue; tf.AutoSize=msoAutoSizeNone
        tf.TextRange.Text=""
        for idx, pd in enumerate(paragraphs):
            txt=pd.get("text","")
            if idx==0: para=tf.TextRange.Paragraphs(1); para.Text=txt
            else:
                tf.TextRange.InsertAfter("\r")
                para=tf.TextRange.Paragraphs(idx+1); para.Text=txt
            run=para.Runs(1) if para.Runs.Count>0 else para
            if "font_size"    in pd: run.Font.Size  =pd["font_size"]
            if "bold"         in pd: run.Font.Bold  =(msoTrue if pd["bold"]  else msoFalse)
            if "italic"       in pd: run.Font.Italic=(msoTrue if pd["italic"]else msoFalse)
            if "color"        in pd: r,g,b=_hex(pd["color"]); run.Font.Color.RGB=_vba(r,g,b)
            if "alignment"    in pd: para.ParagraphFormat.Alignment   =pd["alignment"]
            if "space_before" in pd: para.ParagraphFormat.SpaceBefore =pd["space_before"]
            if "space_after"  in pd: para.ParagraphFormat.SpaceAfter  =pd["space_after"]
        return f"Rich textbox ID:{tb.Id} added slide {slide_index}: {len(paragraphs)} paragraph(s)."
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def add_image(
    slide_index: int, image_path: str,
    left: float, top: float,
    width: float=None, height: float=None
) -> str:
    """Insert an image file onto a slide. Returns the new shape's ID."""
    try:
        prs = _prs()
        slide = _slide(prs, slide_index)
        if not os.path.exists(image_path):
            return f"Image not found: {image_path}"
        pic = slide.Shapes.AddPicture(
            FileName=image_path, LinkToFile=msoFalse, SaveWithDocument=msoTrue,
            Left=left, Top=top,
            Width=width if width else -1, Height=height if height else -1
        )
        if width:  pic.Width  = width
        if height: pic.Height = height
        return f"Image ID:{pic.Id} added to slide {slide_index}: '{os.path.basename(image_path)}' at ({left:.0f},{top:.0f}) {pic.Width:.0f}×{pic.Height:.0f}"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def add_chart(
    slide_index: int, chart_type: int, data: List[Dict[str,Any]],
    title: str="", left: float=60, top: float=120,
    width: float=560, height: float=340
) -> str:
    """Add a chart. chart_type: 51=Col, 4=Line, 5=Pie, 57=Bar.
    data: [{"Label":"Q1","Value":100},...]
    """
    try:
        prs = _prs()
        slide = _slide(prs, slide_index)
        cs = slide.Shapes.AddChart(chart_type, left, top, width, height)
        c = cs.Chart
        if title: c.HasTitle=True; c.ChartTitle.Text=title
        if data:
            cd=c.ChartData; cd.Activate(); wb=cd.Workbook; ws=wb.Worksheets(1)
            keys=list(data[0].keys())
            for ci,k in enumerate(keys): ws.Cells(1,ci+1).Value=k
            for ri,row in enumerate(data):
                for ci,k in enumerate(keys): ws.Cells(ri+2,ci+1).Value=row.get(k,"")
            wb.Close(SaveChanges=True)
        return f"Chart (type {chart_type}) added to slide {slide_index}."
    except Exception as e:
        return f"Error: {e}"


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 7 — Z-ORDER & SHAPE MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def send_shape_to_back(slide_index: int, shape_identifier: str) -> str:
    """Send a shape behind all others. Use on background panels added with add_shape()
    so they don't cover text boxes or template images.
    """
    try:
        prs = _prs()
        sh = _find(_slide(prs,slide_index), shape_identifier)
        if not sh: return f"Shape '{shape_identifier}' not found."
        sh.ZOrder(msoSendToBack)
        return f"'{shape_identifier}' sent to back."
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def bring_shape_to_front(slide_index: int, shape_identifier: str) -> str:
    """Bring a shape in front of all others."""
    try:
        prs = _prs()
        sh = _find(_slide(prs,slide_index), shape_identifier)
        if not sh: return f"Shape '{shape_identifier}' not found."
        sh.ZOrder(msoBringToFront)
        return f"'{shape_identifier}' brought to front."
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def delete_shape(slide_index: int, shape_identifier: str) -> str:
    """Delete a shape by ID or Name. Use to remove Google Shapes and leftover imports."""
    try:
        prs = _prs()
        sh = _find(_slide(prs,slide_index), shape_identifier)
        if sh: sh.Delete(); return f"'{shape_identifier}' deleted from slide {slide_index}."
        return f"Shape '{shape_identifier}' not found."
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def copy_shape_to_slide(source_slide: int, shape_identifier: str, target_slide: int) -> str:
    """Copy a shape from one slide to another (logos, accent bars, decorative elements)."""
    try:
        prs = _prs()
        sh = _find(_slide(prs,source_slide), shape_identifier)
        if not sh: return f"Shape '{shape_identifier}' not found on slide {source_slide}."
        sh.Copy(); _slide(prs,target_slide).Shapes.Paste()
        return f"'{shape_identifier}' copied: slide {source_slide} → {target_slide}."
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def set_slide_background(slide_index: int, color: str) -> str:
    """Set a solid background color on a slide.
    WARNING: Only use this if the slide has NO template background image.
    Check get_slide_info() first — if there's a Picture shape covering the slide, don't use this.
    """
    try:
        prs = _prs()
        slide = _slide(prs, slide_index)
        r,g,b=_hex(color)
        slide.Background.Fill.Solid()
        slide.Background.Fill.ForeColor.RGB=_vba(r,g,b)
        slide.FollowMasterBackground=msoFalse
        return f"Slide {slide_index} background → {color}."
    except Exception as e:
        return f"Error: {e}"


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 8 — QUALITY AUDIT
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def audit_presentation() -> str:
    """Full quality check of the presentation.
    Detects:
    - Overlapping text shapes
    - Fonts below 13pt
    - Out-of-bounds elements (x < 0 or x+w > 970)
    - Leftover Google Shape imports
    - Unedited placeholder text

    Fix ALL issues before saving.
    """
    try:
        prs = _prs()
        kw  = ["clique para","click to","lorem ipsum","título do slide",
               "texto aqui","[insira]","slide title","type here",
               "our   aim","the  goal","goals inside","an aim in"]
        report = ["AUDIT REPORT\n"]
        total  = 0

        for i in range(1, prs.Slides.Count+1):
            slide = prs.Slides(i)
            issues = []
            shapes = []

            for j in range(1, slide.Shapes.Count+1):
                s = slide.Shapes(j)
                info = {"id":s.Id,"name":s.Name,
                        "l":s.Left,"t":s.Top,"w":s.Width,"h":s.Height,
                        "r":s.Left+s.Width,"b":s.Top+s.Height,
                        "text":"","font_size":0}
                if s.HasTextFrame:
                    info["text"] = s.TextFrame.TextRange.Text.strip()
                    try: info["font_size"] = s.TextFrame.TextRange.Font.Size
                    except: pass
                shapes.append(info)

                if "Google Shape" in s.Name:
                    issues.append(f"  ⚠ GOOGLE IMPORT: '{s.Name}' ID:{s.Id} — delete with delete_shape({i}, '{s.Name}')")

            # Out-of-bounds
            for s in shapes:
                if s["l"] < -5 or s["r"] > SLIDE_W+5:
                    issues.append(f"  ⚠ OUT-OF-BOUNDS '{s['name']}': L={s['l']:.0f} R={s['r']:.0f}")

            # Overlapping text
            ts = [s for s in shapes if s["text"]]
            for a in range(len(ts)):
                for b in range(a+1,len(ts)):
                    s1,s2=ts[a],ts[b]
                    if not(s1["l"]>=s2["r"] or s1["r"]<=s2["l"] or s1["t"]>=s2["b"] or s1["b"]<=s2["t"]):
                        issues.append(f"  ⚠ OVERLAP '{s1['name']}' ↔ '{s2['name']}' → smart_layout_vertical({i})")

            # Tiny fonts
            for s in shapes:
                if s["text"] and 0 < s["font_size"] < 13:
                    issues.append(f"  ⚠ TINY FONT '{s['name']}': {s['font_size']:.0f}pt (min 13)")

            # Placeholder text
            for s in shapes:
                if any(k in s["text"].lower() for k in kw):
                    issues.append(f"  ⚠ PLACEHOLDER '{s['name']}': still has template/import text")

            if issues:
                report.append(f"Slide {i}:"); report.extend(issues); report.append("")
                total += len(issues)

        if total == 0: report.append("✅ All clear.")
        else:          report.append(f"Total: {total} issue(s) — fix before saving.")
        return "\n".join(report)
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def smart_layout_vertical(slide_index: int, margin: float=12.0, start_top: float=None) -> str:
    """Auto-stack text shapes vertically without overlapping.
    Sorts by current Top and repositions sequentially.
    margin: gap between shapes in points. start_top: override Y start.
    """
    try:
        prs = _prs()
        slide = _slide(prs, slide_index)
        ts = [slide.Shapes(i) for i in range(1,slide.Shapes.Count+1)
              if slide.Shapes(i).HasTextFrame and slide.Shapes(i).TextFrame.TextRange.Text.strip()]
        if not ts: return "No text shapes found."
        ts.sort(key=lambda s: s.Top)
        cur = start_top if start_top is not None else ts[0].Top
        out = []
        for sh in ts:
            sh.Top=cur; out.append(f"  '{sh.Name}' → T={cur:.0f}")
            cur += sh.Height + margin
        return f"Slide {slide_index} re-stacked:\n"+"\n".join(out)
    except Exception as e:
        return f"Error: {e}"


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 9 — SAVE
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def save_presentation(file_path: str) -> str:
    """Save the active presentation to a .pptx file."""
    try:
        prs = _prs()
        file_path = str(Path(file_path).resolve())
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        prs.SaveAs(file_path)
        return f"Saved: {file_path}"
    except Exception as e:
        return f"Error: {e}"


if __name__ == "__main__":
    mcp.run()