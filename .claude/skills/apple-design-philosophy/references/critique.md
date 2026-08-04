# Running a critique

How to deliver judgement so it changes the work. Read this when reviewing someone's design or code, or when auditing your own before presenting it.

## Contents

- [The failure mode of reviews](#the-failure-mode-of-reviews)
- [Structure](#structure)
- [Ranking findings](#ranking-findings)
- [How to phrase it](#how-to-phrase-it)
- [Diagnosing "it feels off"](#diagnosing-it-feels-off)
- [Worked examples](#worked-examples)
- [When restraint is the wrong answer](#when-restraint-is-the-wrong-answer)

## The failure mode of reviews

A review that lists twenty equal-weight observations communicates nothing, for the same reason an interface that emphasises everything emphasises nothing. The reader cannot tell what matters, so they either fix the easy items and miss the important one, or they disengage entirely.

**Apply the skill's own principles to the review itself.** One primary finding. Supporting findings ranked beneath it. Everything that does not earn its place, cut.

## Structure

Use this shape. It front-loads the thing that matters, which is the only part guaranteed to be read.

1. **The core problem, in one or two sentences.** The single change with the largest effect. If there is genuinely nothing significant, say that plainly and stop; manufacturing a headline finding to seem thorough is its own failure.
2. **Why it costs.** What the user or the next engineer actually experiences. Not "this violates a principle," but the concrete consequence.
3. **What to do instead.** Specific and actionable. A criticism without a proposal is an obstacle.
4. **Secondary findings, ranked.** Three to five at most. More than that and you are inventorying, not reviewing.
5. **What is working.** Brief and specific, and only if true. This is not politeness padding: naming what works tells the author what to protect during the fix, which is real information they cannot get elsewhere.

## Ranking findings

Rank by cost, not by how easy the problem is to see.

**Highest cost first:**
- Wrong hierarchy. The user cannot tell what matters, which corrupts every interaction on the surface.
- Unearned surface area or an option that should have been a decision, because these are effectively permanent.
- Something that fails in a real state (empty, overflowing, failing) that was designed only for the ideal one.
- Complexity forwarded to callers rather than absorbed.

**Middle:**
- Broken consistency with no stated reason.
- Decoration standing in for structure.
- Names that do not predict behaviour.

**Lowest, and often not worth raising at all:**
- Individual spacing and alignment nits, unless they are systemic. One misaligned element is a fix; a layout with no shared alignment is a finding.

A useful filter: **if it would not survive the author asking "so what," it does not belong in the review.**

## How to phrase it

**Name the specific thing, not the category.** "The three filled buttons compete, so the eye lands nowhere" beats "improve visual hierarchy," which is unactionable and mildly insulting.

**State the consequence, not the rule.** "A user scanning this cannot tell which action is primary" beats "this violates the one-primary-action principle." Rules invite argument about rules; consequences invite fixes.

**Be direct without being cold.** The work is not the person. "This section does not earn its place" is fine. "Why would you do this" is not, and it makes the actual point harder to hear.

**Say when you are uncertain.** "I think the density here is a problem, though it depends on whether users scan or read this page" is more useful than false confidence, because it tells the author what to check.

**Do not soften a real finding into invisibility.** Hedging an important problem until it reads as optional is a failure of the review. Be kind about the person and unambiguous about the work.

## Diagnosing "it feels off"

When someone cannot name what is wrong, work this list in order. The cause is usually in the first three.

1. **Hierarchy.** Rank elements by importance, then by visual weight. Mismatches here are the most common root cause by a wide margin, and they masquerade as "it looks cluttered."
2. **Spacing.** Is the space within groups smaller than the space between them? When these are equal, structure disappears and everything reads as one undifferentiated field.
3. **Alignment.** Is everything aligned to something, and to as few lines as possible? Stray alignments read as sloppiness without being consciously noticed.
4. **Type.** Too many sizes, steps too close together, line height uniform across sizes, measure too wide.
5. **Colour.** Too many hues, hue carrying meaning alone, or saturated colour over too much area.
6. **Depth.** Elevation applied evenly, so it encodes nothing.
7. **Density.** Everything present at once because nothing was deferred.

For "this code feels wrong," the parallel list: surface area too large, names that do not predict behaviour, complexity forwarded rather than absorbed, layers that only forward, options that should have been decisions.

## Worked examples

### Example 1: dashboard header

**Before.** A page header with a title, a subtitle, a coloured status chip, a "Last updated" line, a search field, three filled buttons (Export, Share, New), and a bordered card wrapping all of it.

**The core finding.** Three filled buttons means no primary action, so the eye lands nowhere and the user has to read all three. Only one of them is the reason people come to this page.

**The critique.**
> The three filled buttons compete, and the result is that none of them reads as primary. "New" is the action this page exists for; Export and Share are occasional. Make "New" the only filled button, demote Export and Share to text buttons or a menu, and the header will resolve immediately.
>
> Secondary: the card border around the header is doing no work, because the header is already separated from the content by position and space. Removing it gives you back the horizontal room the buttons need. "Last updated" and the status chip are saying related things in two visual languages; fold the timestamp into the chip or drop it.
>
> The search field placement is good, and the title/subtitle relationship is clear. Keep those as you rework the rest.

**Note the shape:** one finding with a reason and a fix, two supporting cuts, one honest note about what to protect. Not eight bullet points of equal weight.

### Example 2: a service module

**Before.**

```python
class DataManager:
    def process(self, data, validate=True, retry=False, async_mode=False,
                cache=True, verbose=False):
        ...
```

**The core finding.** The signature forwards complexity instead of absorbing it. Six flags means sixty-four behavioural combinations, and the caller must understand all of them to use any of them.

**The critique.**
> This signature asks the caller to make six decisions they are not equipped to make. `process(data, True, False, True)` is unreadable at the call site, and the sixty-four combinations are neither tested nor meaningfully distinct: `retry=True, async_mode=False` almost certainly is not a real use case anyone chose.
>
> Find the two or three combinations that actually occur in the codebase and give them names. If nearly every caller passes `validate=True, cache=True`, those are not options, they are the behaviour, and the flags exist because nobody wanted to decide.
>
> `DataManager` and `process` also tell the reader nothing. What data, and what does processing do to it? A name that predicts behaviour would let most readers skip the implementation entirely, which is the point.

### Example 3: pushing back on a request

**The request.** "Add a settings toggle so users can choose whether the sidebar starts collapsed."

**The critique.**
> Worth asking what this costs before building it. A toggle is permanent: it needs persistence, a settings entry, documentation, and it doubles the initial states every future sidebar change has to be tested against.
>
> The underlying question is whether the sidebar should start collapsed, and that is answerable. If it is mostly navigation people use once per session, default collapsed. If it carries live state people watch, default open. Remembering the user's last manual choice gets most of the benefit with no settings surface at all, since it is inferred rather than configured.
>
> If there is evidence the population is genuinely split and the preference is strong, the toggle earns its place. That evidence is worth having before the option ships, because options are far easier to add than to remove.

## When restraint is the wrong answer

Strictness misapplied is its own failure, and this skill should not become a reflex to delete things.

**Removing something load-bearing is the same error as keeping something useless.** If an element survives the Earn Test, defend it as firmly as you cut the others.

**Density is sometimes correct.** A trading terminal, an analytics table, or a professional tool used for hours by experts should be dense. Deference means serving the content, and when the content is a hundred simultaneous values, whitespace between them costs the user real work. Do not impose consumer-app airiness on a professional instrument.

**Some domains need redundancy.** Safety-critical confirmations, accessibility affordances, and legally required disclosures are not clutter, even when they add elements. The Earn Test handles this correctly: they have a job and something breaks without them.

**Familiar beats elegant.** A conventional pattern users already know usually beats a cleaner one they have to learn. Novelty has a cost paid by the user, not the designer.

**Consistency can be wrong.** If the established pattern is bad, matching it propagates the problem. Change it deliberately and completely, rather than either matching it silently or breaking it silently.

The through-line: the goal is not less. The goal is that everything present has a reason, and that the reason can be stated.
