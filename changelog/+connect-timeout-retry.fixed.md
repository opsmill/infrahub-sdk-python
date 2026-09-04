Treat `httpx.ConnectTimeout` like other connection failures: it is raised as `ServerNotReachableError` and retried when `retry_on_failure` is enabled, instead of escaping as a raw httpx exception.
