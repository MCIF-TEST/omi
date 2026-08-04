# Backend and systems practice

The same judgement, applied where there is nothing to look at. Read this when the work is server-side, architectural, or library design: modules, APIs, naming, errors, configuration, data models.

## Contents

- [The central idea: absorb complexity](#the-central-idea-absorb-complexity)
- [Surface area](#surface-area)
- [Naming](#naming)
- [Parameters and signatures](#parameters-and-signatures)
- [Errors](#errors)
- [Configuration](#configuration)
- [Data and types](#data-and-types)
- [Architecture and layering](#architecture-and-layering)
- [Consistency](#consistency)
- [Comments and documentation](#comments-and-documentation)
- [Applying the seven principles](#applying-the-seven-principles)

## The central idea: absorb complexity

Apple's "complexity is hidden" has an exact engineering counterpart: **a good module has a simple interface and a substantial implementation.** It takes on difficulty so its callers do not have to.

The measure of a module is the ratio between what it does and what you must know to use it. A module that handles retries, backoff, connection reuse, and pagination behind a single method has a large ratio and is worth its existence. A wrapper that requires almost as much understanding as the thing it wraps has a ratio near one, and it is pure cost: another name to learn, another file to open, another layer to step through in a debugger.

**Shallow abstraction is the backend equivalent of visual clutter.** Both add an element that does not carry its weight, and both are defended the same way ("it is only a small one"), and both accumulate.

The diagnostic question for any abstraction:

> Does this make the caller's life simpler, or does it only make my file shorter?

Moving complexity is not removing it. If your function became clean because every caller now handles a special case, you did not simplify the system, you distributed the mess and made it harder to see.

## Surface area

**Every public name is a permanent promise.** Once something is exported, someone depends on it, and removing it becomes a breaking change. This asymmetry between how easy it is to add and how hard it is to remove is why surface area only ever grows unless someone actively resists.

**Default to private.** Export when there is a caller, not in anticipation of one. "Someone might need this" reliably produces API nobody needs and everybody maintains.

**Fewer, stronger entry points.** One well-designed function that handles the real use case beats five primitives that make the caller assemble it, because assembly is exactly the complexity you were supposed to absorb.

**Deprecate deliberately.** If something must go, mark it, give the replacement in the message, and set a removal date. Silent removals train people not to trust upgrades; permanent deprecation trains them to ignore warnings.

## Naming

A name is the entire interface for most readers most of the time. They will read the name a hundred times and the implementation once, if ever.

**A name should let a reader predict behaviour without opening the body.** That is the whole standard.

**A name that needs a comment to explain it is the wrong name.** Fix the name and delete the comment. `dataManager` needing "handles user session persistence" should have been `sessionStore`.

**Precision beats brevity, and brevity beats explanation.** `retryCount` beats `n`, and it beats `numberOfTimesToRetryTheRequest`. Aim for the shortest name that is still unambiguous in context.

**Avoid vague nouns.** `Manager`, `Handler`, `Processor`, `Util`, `Helper`, and `Service` usually mean the author had not decided what the thing was. A file called `utils.py` becomes a landfill in every codebase that has one, because nothing is ever out of place in it.

**Booleans read as assertions.** `isReady`, `hasAccess`, `shouldRetry`. Negated names double the cognitive cost, since `if (!isNotReady)` forces the reader to unwind two negations.

**Say the same thing the same way everywhere.** If it is `user_id` in one place, it is not `userId`, `uid`, and `account` elsewhere. Synonyms make the reader wonder what distinction they are missing, and occasionally there really is one, which is worse.

**Names should reflect the domain, not the mechanism.** `cache` describes how; `recentlySeenAccounts` describes what. The second survives replacing the cache.

## Parameters and signatures

**Boolean parameters are unreadable at the call site**, which is the only place readability matters. `render(true)` tells you nothing. Use an enum, a named option, or two functions. `render({ compact: true })` or `renderCompact()` both work.

**More than three or four positional parameters means the reader must count commas.** Group related ones into an object or struct that names them.

**Options objects need good defaults.** If the common case requires passing options, the defaults are wrong. The right default is the one most callers would have chosen, so most callers should pass nothing.

**Do not take parameters you only forward.** A parameter that exists solely to be handed to a dependency is a sign the layering is wrong: the caller now knows about something two levels down.

**Make the common case short and the rare case possible.** If the ninety percent path needs three lines of setup, the design has optimised for the ten percent.

## Errors

An error is the interface's behaviour under failure, which is when the user needs it most and has the least patience.

**An error should answer three questions:** what happened, what was expected, and what to do about it. Most errors answer only the first, and vaguely.

Weak: `ValueError: invalid configuration`

Strong: `Invalid configuration: 'timeout' is 0, expected a positive integer (seconds). Set OMI_TIMEOUT or pass timeout= explicitly.`

The second is longer, and length is not the cost people think it is. The cost is the half hour someone spends bisecting to find what the first one meant.

**Include the offending value.** "Expected a positive integer" without showing what arrived leaves the reader guessing, and the value is usually the entire clue.

**Fail fast and loudly at boundaries.** Validate at the edge where the bad data enters. A malformed value that flows three layers deep before failing produces a stack trace pointing at a victim rather than a cause.

**Never swallow an exception silently.** An empty catch block is a bug with a delay fuse. If a failure is genuinely acceptable, log it and say why in the code, because "this can fail harmlessly" is exactly the kind of claim that stops being true.

**Watch for failures with no visible signature.** Background jobs, worker pools, and fire-and-forget tasks that absorb their exceptions produce features that simply never happen, with nothing in the logs and no error to search for. These are the most expensive bugs in any system, because nobody is looking for a thing that failed quietly.

## Configuration

**Every option is permanent complexity.** It doubles the state space you must reason about and test, and it must be documented, validated, and supported forever. Options are the backend's decorative shadows: individually harmless, collectively suffocating.

**An option added because the team could not decide is a decision deferred onto every user.** Make the call. Users overwhelmingly want a system that works, not a system they must configure to work.

**Defaults should be right, not neutral.** Choosing a safe-looking default that nobody wants (a timeout of zero, a cache size of one) is still choosing, just badly.

**Validate configuration at boot, and refuse to start when it is incoherent.** A service that starts in a broken state and fails later is much harder to diagnose than one that refuses with a clear reason. This is deference: the system serves the operator's need to know, rather than protecting its own uptime metric.

**Especially refuse to start silently degraded in production.** A missing security setting that quietly disables enforcement is the worst possible default, because the system reports itself healthy while providing none of the guarantee.

## Data and types

**Make illegal states unrepresentable.** A type that permits nonsense will eventually contain nonsense, and the check you were relying on will be in the one code path nobody updated.

**Distinguish absent from empty.** `null` and `""` usually mean genuinely different things: "we never learned this" versus "this is known to be empty." Collapsing them destroys information that is often the actual signal, and it cannot be recovered later.

**Avoid stringly-typed data.** A status held as a free string will accumulate typos, casing variants, and values nobody remembers adding. An enum makes the full set knowable.

**Model the domain, not the storage.** Interfaces shaped around table layout leak schema decisions to every caller and freeze the schema in place.

**Be conservative about what you store and honest about what you keep.** Data you did not collect cannot leak, and this is a design property rather than a policy one.

## Architecture and layering

**Dependencies point one direction.** Cycles mean the boundary is imaginary, and everything in the cycle is really one module that has been split for filing purposes.

**A layer should be a real change in abstraction.** If a layer mostly forwards calls, it is a shallow module and deleting it makes the system easier to understand.

**Put the complexity where it is used once, not where it is used everywhere.** Absorb difficulty into a single deep module rather than requiring every caller to handle it correctly. Each caller is another chance to get it wrong.

**Design so the common path is the correct path.** If using the system safely requires remembering something, the design will eventually be used unsafely, and the fix is structural rather than documentary.

**Prefer boring, obvious solutions.** Cleverness has to be paid for by every future reader, in a currency (their attention at the moment they are debugging something else) that is far more expensive than the author's time.

## Consistency

**One way to do a thing.** Two competing patterns turn every future change into a decision, and the decision will be made inconsistently, which compounds.

**Follow the codebase over your own preference.** Arriving in an established codebase and introducing a personal style creates a fork in every file you touch. Match what is there, and if it genuinely needs to change, change it deliberately and everywhere.

**Symmetry is a real signal.** If there is `open`, there should be `close`, not `dispose`. If there is `serialize`, there should be `deserialize`, not `parse`. Broken symmetry makes readers hunt for a distinction that does not exist.

## Comments and documentation

**Comment the why, never the what.** The code says what. A comment restating it is a second copy that will drift out of sync and then actively mislead.

**The most valuable comment records a decision and its cost.** Why this approach over the obvious one, what broke last time, what constraint forces this. That is knowledge the code physically cannot contain, and it is what stops the next person reintroducing a bug that was already paid for once.

**A comment explaining confusing code is a missed refactor.** Try renaming and restructuring first; keep the comment only if the confusion is essential rather than incidental.

**Delete commented-out code.** Version control already has it. It survives only because deleting feels riskier than leaving it, which is exactly the instinct restraint exists to counter.

## Applying the seven principles

| Principle | Backend meaning |
|---|---|
| **Clarity** | Names predict behaviour. Errors state cause and remedy. Reading the signature is enough. |
| **Deference** | The interface serves the caller's task, not the implementer's data model. Internal structure does not leak. |
| **Depth** | Layers encode real abstraction changes. Dependencies point one way. Modules are deep, not shallow. |
| **Restraint** | Minimal public surface. Few options. Nothing exported speculatively. |
| **Consistency** | One way to do a thing. Symmetric names. Uniform conventions across the codebase. |
| **Precision** | Exact types. Illegal states unrepresentable. Boundaries validated where data enters. |
| **Human focus** | Optimised for the reader and the person debugging at 3am. Common path is the correct path. |
