---
paths:
  - "infrahub_sdk/**/*.py"
---

# Component design (SOLID / DI)

Applies when creating a new component or making significant changes to an existing one. Does not apply to small bug fixes, single-function tweaks, or changes confined to existing code paths. When in doubt for anything that introduces a new class or reshapes responsibilities, follow this rule.

## Use modular components with dependency injection

New logic should live in components that receive their collaborators through constructor injection rather than instantiating them internally. This keeps components composable, swappable, and testable without patching.

## Required dependencies, not optional

Constructor dependencies for new code are required parameters - not `collaborator: Collaborator | None = None` with an internal default. Optional injection hides that the dependency exists and lets a caller silently skip wiring it. Make every collaborator an explicit, required constructor argument - explicit is better than implicit.

The single exception is editing existing code where adding a required parameter would force a large change across many call sites. There, an optional parameter is a transitional compromise to keep the change small - not the target shape for new components.

Late registration is the same anti-pattern in another shape. `set_collaborator(x)`, `register_handler(fn)`, or assigning `obj.on_change = fn` after construction hides the dependency at construction, lets a caller skip wiring it, lets a second caller silently clobber the first's, and forces a `None` check at every use site. Pass it to `__init__`. When the component feeds zero or more collaborators rather than exactly one, that argument is a required `list[...]`, and callers with nothing to wire pass `[]` explicitly.

## Build components near the entry point

Construct components as close to the entry point as possible. In this repository the entry points are the client constructors (`InfrahubClient` / `InfrahubClientSync`) and the `infrahubctl` command functions - those are the composition roots. `infrahub_sdk/ctl/exporter.py` is the worked example: the command resolves the client and the console, builds the exporter with them, and delegates - the exporter never reaches for a client of its own.

Use a builder class or factory function when wiring is non-trivial, and inject each sub-component rather than constructing it inside a parent component's `__init__`.

Anything that comes from outside the component's own domain - resolved configuration, a transport, a console, a logger - is resolved at that entry point, never inside the component:

- **Configuration resolves at the entry point, not in the component.** A component takes plain values (`max_retries: int`, `backoff_base: float`), never a `Config` object and never a module-global read. `RateLimitRetryHandler` is the example to copy: the client reads `self.config.rate_limit_*` once and passes plain numbers down, so the handler is the only thing that has to be understood to test the retry decisions, and it is testable with hand-picked values.
- **A factory takes its out-of-domain collaborators as parameters too**, rather than choosing them. A factory that both reads config *and* picks the concrete implementations has only moved the coupling one level out; take them as arguments so the entry point names them and the factory stays reusable with different ones.
- **Configure at construction, never by assignment afterwards.** Reaching into a built object to finish setting it up leaves a window in which it is misconfigured, makes a fixed value look mutable, and scatters the wiring across two places. Pass it to `__init__`, and expose it through a read-only property if callers need to read it back.
- **Avoid mutable module-level registries.** A dict at module scope that other modules write into makes behaviour depend on which imports have run and leaks between tests in the same worker. Prefer passing the mapping into the factory, so the entry point names what is registered.

## Single entry point, operating on arguments

A component should generally expose a single public entry point method (occasionally more, when justified by cohesive responsibility). That method only accepts the entities being operated on as arguments - it should not require additional dependencies to be passed in alongside the work payload. `LineDelimitedJSONExporter.export(...)` is the shape: the client arrives in the constructor, the export directory, namespaces and branch arrive per call.

## Constructor vs. method arguments

- The client (or requester) is always injected to the constructor.
- `branch` is usually injected to the constructor, but not always - inject it when the component's lifetime is tied to a single branch; pass it per-call when the component is reused across branches.
- Entities being examined or updated (nodes, schemas, spec payloads, file contents, request parameters) are passed to the entry method, not stored on the instance.

The boundary is: long-lived collaborators go in the constructor; transient work items go in the method.

## Single Responsibility Principle

Each component should have one reason to change. If a class is doing two unrelated things, split it. Prefer composition of small components over large multi-purpose ones.

## Keep decision logic out of the async/sync split

Every public feature ships in both an async and a sync variant, so any logic written inside the two variants is written twice and drifts. Put the decision logic in a plain component with no I/O, have both variants call it, and duplicate only the awaiting.

`RateLimitRetryHandler` splits exactly this way: `parse_retry_after`, `compute_backoff` and `should_retry` are pure and shared, and only `send` / `asend` exist twice, because only they perform I/O. The pure half is then covered once by tests that need no transport at all.

The corollary is a design test: if a rule can only be exercised through an awaited call, it is probably sitting on the wrong side of that line.

## Interfaces for multiple implementations

When more than one implementation of a component is required (different formats, different backends, a no-op variant), define a `Protocol` or abstract base class. The correct implementation is selected at the wiring layer and injected to the constructor - the consumer codes against the interface, not a concrete class. `ExporterInterface` / `ImporterInterface` (`infrahub_sdk/transfer/`) and `DataProcessor` (`infrahub_sdk/spec/processors/`) are the existing examples.

A single implementation does not need an interface yet; introduce one when the second implementation arrives. Note that the second implementation can be either a no-op version or a testing version of a component.

## Interfaces to keep an out-of-domain dependency out

The other reason to declare a `Protocol` is to invert a dependency direction, and there **one implementation is enough**. The situation: a component's logic has no business knowing about some out-of-domain concern - logging, a recorder, a progress display, telemetry - but something has to feed that concern from inside the component's flow. Importing the concrete client directly is what you are avoiding: it makes the dependency viral, drags a third-party package into the import chain of pure logic, and means the component can no longer be constructed in a test without it.

`Recorder` (`infrahub_sdk/recorder.py`) and `InfrahubLogger` (`infrahub_sdk/types.py`) are this pattern already: a `Protocol` the SDK owns, satisfied structurally by whatever the caller supplies.

There are two acceptable shapes for the interface itself. Both keep the adapter and the logic from importing each other; pick one per interface and be consistent within it.

1. **Implicit - a `Protocol` declared beside the consumer, which the adapter never imports.** Structural typing is what makes this work: the adapter satisfies the protocol by having matching signatures, so nothing in the adapter's module points back at the consumer's. This is the lower-friction option: one new class, no new module, and no coordination with the adapter.
2. **Explicit - an interface in a module of its own that both sides import.** Put the `Protocol` (or an ABC, if you want subclassing enforced) in a small, dependency-free interface module; the consumer imports it to type its constructor parameter, and the adapter imports it to declare that it implements it. Neither side imports the other, so the dependency still points inward at the interface, but the contract is now named at both ends: the adapter states what it implements, the type checker verifies it at the definition rather than only at the wiring call, and a reader of the adapter can find the interface without knowing which component motivated it. Explicit is better than implicit - prefer this one whenever the interface is worth naming as a contract, which is the case as soon as it has more than one implementer or more than one consumer. `infrahub_sdk/transfer/exporter/interface.py` is this shape.

An ABC only works in shape 2 - a subclass must import whatever module the base lives in, so an ABC declared in the consumer's module drags the dependency backwards. Never do that; if you want an ABC, give it its own module.

Whichever shape you pick, the remaining two parts do not change:

- **Name the methods in the depending component's vocabulary**, not the adapter's, and pass the values as arguments rather than handing over `self`, so the adapter can never read back into the component. The component then depends on a shape it defined, has no idea what is on the other side, and stays free to change its internals.
- **Put the concrete adapter in a separate, purpose-named module** that is the only place importing the library, and **let only the wiring layer import both** (see "Build components near the entry point").

The acceptance test is an import-graph one: after this, the library is reachable from the entry point and from the adapter module, and from nowhere in the logic. Verify it by grepping for the package name - if it appears anywhere under the component's own package, the split is incomplete.

This is the deliberate exception to "a single implementation does not need an interface yet" above. The interface earns its place by fixing which way the dependency points, not by abstracting over variants - and in practice the test doubles become the second and third implementations anyway.

## Dispatching across implementations

When a component must pick one of several implementations at runtime based on the input, do not branch with `isinstance` (or a `match` on the input's type) inside one class. Give each implementation a predicate on the shared interface (e.g. `supports(request) -> bool`) alongside its entry method, hold the implementations as an injected list in an aggregator component, and let the aggregator delegate to the first that supports the input:

```python
class CheckerInterface(ABC):
    @abstractmethod
    def supports(self, request: Request) -> bool: ...

    @abstractmethod
    def check(self, request: Request) -> Result: ...


class AggregatedChecker:
    def __init__(self, checkers: list[CheckerInterface]) -> None:
        self.checkers = checkers

    def run(self, request: Request) -> Result:
        for checker in self.checkers:
            if checker.supports(request):
                return checker.check(request)
        raise NoCheckerError(request)
```

The aggregator depends only on the interface; the concrete list is assembled by the factory at the wiring layer, so adding an implementation is one new class plus one line in the factory, with no edit to the dispatch logic.

This is for an open, extensible set of implementations. When the set is closed and fixed (an enum, a sealed union), an exhaustive `match` with `typing.assert_never` is the right tool instead.

## Why this design matters

Stepping back from the individual rules above: constructor-injected long-lived dependencies plus method-passed transient entities is the boundary that lets components be reused across calls and substituted with real implementations instead of `unittest.mock`. The [testing rules](./python-testing.md) forbid `unittest.mock` - that prohibition is only practical when production code follows this design.

Use this as a design driver, not just a constraint: the no-mock rule is the forcing function for this structure. When you make a component's decision logic testable without patching - collaborators injected through the constructor, a single entry point that is pure and operates only on its arguments - dependency inversion and single responsibility fall out as the path of least resistance rather than discipline you have to summon. The corollary is a useful smell test: if a component is hard to test without a mock, that is the signal it needs splitting or its dependencies injected, not that it needs a mock.

## Existing code

If existing nearby code violates this pattern, do not refactor it as part of an unrelated change. Raise it as a separate discussion - drive-by refactors balloon scope and make reviews harder.
