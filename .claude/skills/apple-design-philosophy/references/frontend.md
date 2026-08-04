# Frontend practice

Concrete application of the seven principles to interfaces. Read this when the work is UI: layout, type, colour, hierarchy, depth, components, or interface copy.

## Contents

- [Typography](#typography)
- [Spacing and rhythm](#spacing-and-rhythm)
- [Hierarchy](#hierarchy)
- [Colour](#colour)
- [Depth and elevation](#depth-and-elevation)
- [Layout](#layout)
- [Components](#components)
- [Interface copy](#interface-copy)
- [States](#states)
- [Optical adjustments](#optical-adjustments)

## Typography

Type carries most of the meaning in most interfaces, so it is where quality is won or lost first. Fixing type usually removes the perceived need for decoration entirely.

**One family, used well, beats two families used decoratively.** A second family must earn its place with a structural job: a monospace face for data, ids, and evidence is a real job, because it signals "this is raw and exact." A second face for headings because the first felt plain is decoration, and it usually reads as two products stitched together.

**Limit the scale.** Five or six sizes covers nearly every interface. More than that and the steps stop being distinguishable, so the extra sizes convey nothing while multiplying the decisions.

**Size steps need to be visible.** Adjacent sizes should differ by roughly 1.2x or more, or the difference reads as a mistake rather than as a level. `15px` next to `16px` looks like a bug.

**Line height scales inversely with size.** Body text wants roughly 1.5. Large headings want 1.1 to 1.25. Applying one line-height everywhere leaves headings looking loose and body text looking cramped.

**Tighten tracking as size grows.** Large text at default tracking looks gappy. Headings above roughly 32px usually want slightly negative letter-spacing, in the range of -0.01em to -0.03em. Small text, especially uppercase labels, wants slightly positive tracking to stay legible.

**Measure matters.** Body text is comfortable at roughly 45 to 75 characters per line. Long lines cost the reader the return sweep; short lines break rhythm. This is one of the few places a hard number genuinely helps.

**Weight is hierarchy, not decoration.** Prefer two weights (regular and one heavier) over four. If you need a third level of emphasis, reach for size, colour, or space before adding a weight.

**Use tabular figures for numbers that change or align.** Proportional digits make columns jitter and metrics shift as they update, which reads as instability.

## Spacing and rhythm

**Space groups before borders do.** Proximity is the strongest grouping signal available and it costs nothing visually. Reach for a border or a background only when space alone cannot express the grouping, which is rarer than it looks. Most boxes in most interfaces can be deleted in favour of spacing.

**Use a scale, not arbitrary values.** A 4px or 8px base with a small set of steps keeps rhythm coherent. Arbitrary values are how interfaces drift: one `13px` margin becomes ten, and the rhythm dies by a thousand cuts.

**Space between groups must exceed space within them.** This is the most common spacing failure. When the gap inside a group equals the gap between groups, the eye cannot parse the structure, and the layout reads as an undifferentiated field of stuff.

**Whitespace is doing work.** It sets pace, indicates importance, and gives the eye somewhere to rest. Space around an element is a claim about its significance. Filling space because it looks empty is how a considered layout becomes a dense one.

## Hierarchy

**Exactly one primary focus per view.** Ask what the user came for, and make sure it is unambiguously the loudest thing. Two competing focal points is not double the emphasis, it is zero.

**One filled button per view, as a rule of thumb.** Multiple filled buttons force a choice the design should have made. Secondary actions take outline or text treatment, and destructive actions should be quiet until the moment of confirmation.

**Establish hierarchy with position and space before colour and weight.** The top-left of a reading order carries weight for free. Spend colour and weight only after the cheap tools are exhausted.

**Progressive disclosure over density.** Show what is needed now, and let the rest be reachable. This is deference in layout form. The test is whether a first-time user can find the main action within a couple of seconds.

## Colour

**Colour is meaning, and meaning is scarce.** Each hue in the system should map to a concept: identity, a state, a category. Once a hue means something, using it decoratively elsewhere corrodes the meaning everywhere.

**Never carry meaning by hue alone.** Roughly one in twelve men has a colour vision deficiency. Pair colour with a label, an icon, a shape, or position. This is an accessibility requirement and it also survives greyscale printing and screenshots.

**Respect contrast minimums.** 4.5:1 for body text, 3:1 for large text and meaningful non-text elements. Treat these as floors, not targets. Text that only just passes at 4.5:1 is uncomfortable in sunlight, on a cheap panel, or for anyone over forty.

**Most of the surface should be neutral.** Interfaces that read as premium are mostly greys with colour used sparingly and precisely. Saturated colour spread widely is the fastest way to look cheap, because it removes the contrast that makes accent colour mean anything.

**Semantic colour needs a full ramp, not one value.** A state colour needs a text-safe variant, a fill variant, and a background tint, since one hex will fail contrast in at least one of those roles.

## Depth and elevation

**Each level of elevation must correspond to a structural fact.** Base surface, raised surface, overlay, and modal is usually the entire ladder an application needs. More levels than that and the distinctions stop being readable.

**Prefer tone over shadow.** A slightly lighter surface reads as elevated with less noise than a drop shadow, and it stays clean on dark backgrounds where shadows either disappear or turn muddy.

**Shadows should imply a consistent light source.** Mixed shadow directions read as broken. Keep the offset vertical and consistent, and keep it soft.

**Translucency is for material, not for style.** A blurred layer says "the thing behind is still there and still relevant." When that is not true, translucency is just a legibility tax on the text sitting over it.

**No glow.** Glow implies emission, which almost nothing in an interface actually does. It is the most common way a serious product ends up looking like a toy.

## Layout

**Alignment creates invisible lines, and the eye follows them.** Every element should align to something. Elements aligned to nothing are the most common source of "this feels sloppy" that people cannot articulate.

**Fewer alignment points is stronger.** One left edge shared by everything beats four edges each shared by two things.

**Constrain measure independently of the container.** A text column should not stretch to fill a wide screen just because the screen is wide.

**Design the narrow case honestly.** Not by shrinking the wide layout, but by asking what matters when there is no room. Mobile is where hierarchy decisions get tested, because everything cannot be prominent when only one thing fits.

**Watch text columns beside fixed-width clusters.** A flexible text column next to a non-shrinking group of buttons will collapse to near-zero width before the buttons give up any space, producing two characters per line. Stack them at narrow widths instead.

## Components

**A component's props are its public interface**, and everything in `references/backend.md` about surface area applies unchanged. Every prop is a promise, permanent from the moment something depends on it.

**Variants should be finite and named after meaning, not appearance.** `primary` and `danger` survive a redesign. `blue` and `red` become lies the moment the palette shifts.

**Prefer composition over configuration.** A component with fifteen props that shape its internals should probably accept children instead. Configuration explodes combinatorially, and composition does not.

**A component that renders differently in six places is six components wearing a trench coat.** Splitting it is usually the honest move.

## Interface copy

Copy is design. It occupies the same space, sets the same tone, and fails in the same ways.

**Say what happens, not what the interface is.** "Delete project" beats "Click here to delete." The user can see the button.

**Front-load the meaningful word.** People scan the first two or three words. "Export as CSV" beats "You can export this data as a CSV file."

**Errors need three things:** what happened, why, and what to do next. "Invalid input" has none of them. "Email address is missing an @" has all three implicitly, which is why it is a better error despite being shorter.

**Buttons are verbs.** "Save changes" beats "OK" because the button should be readable without the dialog text.

**Cut hedging and filler.** "Please note that you may want to consider" is nine words of nothing. Removing them is the copy equivalent of removing a border.

## States

Every view has more states than the designed one, and the designed one is often the rarest in production.

- **Empty.** The first thing a new user sees. It should teach, not apologise. A blank panel with "No data" wastes the highest-attention moment the product gets.
- **Loading.** Reserve the space the content will occupy so nothing jumps. Layout shift is the clearest signal of an unconsidered interface.
- **Partial.** Show what has arrived rather than blocking on everything.
- **Overflowing.** Long names, many rows, unexpected scripts. Test with real values, including non-Latin ones, not with "Example Item."
- **Error.** Say what to do next. Preserve the user's work without exception.
- **Sparse.** One row of a table designed for fifty usually looks broken and needs its own treatment.

## Optical adjustments

Where the eye and the arithmetic disagree, the eye is right. It is the only client.

- **Triangles and asymmetric icons** need nudging toward their visual centre of mass. A play triangle centred by bounding box always looks left-heavy.
- **Circles need to overshoot.** A round shape must be slightly larger than a square to read as the same size, because it encloses less area at every point but the widest.
- **Text sits high in its box.** Cap height and baseline mean a mathematically centred label looks slightly high, so vertical padding usually needs a little more above than below.
- **Heavy shapes at large sizes need looser tracking than the maths suggests**, and bold text needs marginally more line height than regular at the same size.
- **Punctuation and bullets can hang** outside the text edge so the text block itself aligns optically.
- **Borders eat space.** A 1px border on a box changes its optical weight more than its measured size, which is why bordered and unbordered elements at identical dimensions do not look the same size.
