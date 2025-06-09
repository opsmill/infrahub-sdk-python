from __future__ import annotations

import asyncio
import inspect
from functools import partial, wraps
from typing import Any, Callable

from typer import Typer


class AsyncTyper(Typer):
    """
    A Typer subclass that allows to run async functions.

    It overrides the `callback` and `command` decorators to wrap async functions
    in `asyncio.run`.
    """

    @staticmethod
    def maybe_run_async(decorator: Callable, func: Callable) -> Any:
        """
        Wraps an async function in `asyncio.run` if it's a coroutine function.

        Args:
            decorator: The decorator to apply (e.g., from `super().command`).
            func: The function to potentially wrap.

        Returns:
            The decorated function, possibly wrapped to run asyncio.
        """
        if inspect.iscoroutinefunction(func):

            @wraps(func)
            def runner(*args: Any, **kwargs: Any) -> Any:
                return asyncio.run(func(*args, **kwargs))

            decorator(runner)
        else:
            decorator(func)
        return func

    def callback(self, *args: Any, **kwargs: Any) -> Any:
        """
        Overrides the Typer.callback decorator to support async functions.

        Args:
            *args: Positional arguments for Typer.callback.
            **kwargs: Keyword arguments for Typer.callback.

        Returns:
            A decorator that can handle both sync and async callback functions.
        """
        decorator = super().callback(*args, **kwargs)
        return partial(self.maybe_run_async, decorator)

    def command(self, *args: Any, **kwargs: Any) -> Any:
        """
        Overrides the Typer.command decorator to support async functions.

        Args:
            *args: Positional arguments for Typer.command.
            **kwargs: Keyword arguments for Typer.command.

        Returns:
            A decorator that can handle both sync and async command functions.
        """
        decorator = super().command(*args, **kwargs)
        return partial(self.maybe_run_async, decorator)
