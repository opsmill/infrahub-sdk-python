Two declared lower bounds were wrong and have been corrected.

`typer` now requires `>=0.16.0`, up from `>=0.15.0`. Combined with the `click>=8.3` the SDK already required, typer 0.15 crashed on any `infrahubctl --help` with `TypeError: Parameter.make_metavar() missing 1 required positional argument`, because click 8.3 changed that signature and typer only adapted in 0.16. The old floor advertised a combination that could not work.

`Jinja2` now requires `>=3.1.5`, up from `>=3`. On 3.1.4 and earlier, template error reporting points at the wrong template when a nested template uses an undefined variable, and omits the source path when an imported template is missing.

If you pin either package below its new floor, installing the SDK now fails while resolving instead of breaking once you run it.
