Reading the variables of a string Jinja2 template is now cached per template text. The new function `get_template_variables()` in `infrahub_sdk.template` returns the sorted list without building a `Jinja2Template`, and raises `TypeError` when the template is not a string. `Jinja2Template.get_variables()` uses the cache for a string template unless globals, tests or extensions were added to the environment of the template object, or a subclass overrides `_get_string_based_environment()`. In those cases, and for a file-based template, the template is still parsed on every call.

When the cache is used, two errors change:

- A filter that the template object does not provide no longer makes `get_variables()` raise `jinja2.exceptions.TemplateAssertionError`. `validate()` and `render()` still reject that filter.
- A test name that Jinja2 does not provide, used in an expression such as `{{ name is not_a_test }}`, now raises `JinjaTemplateSyntaxError` instead of `jinja2.exceptions.TemplateAssertionError`. `JinjaTemplateSyntaxError` is not a Jinja2 exception, so `except jinja2.TemplateError` no longer catches it.
